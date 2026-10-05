import html
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_db
from app.db.tenant_context import set_tenant_context
from app.models.identity import User
from app.schemas.acquisition import CaptureIn, CaptureOut, CaptureResult
from app.schemas.common import Envelope
from app.schemas.crm import LeadOut, LeadScoreOut
from app.services.acquisition import capture_inbound, hold_interest, interest_is_eligible
from app.services.crm import latest_lead_score
from app.services.orchestrator import process_pending_events
from app.services.public_forms import resolve_form_key

router = APIRouter(prefix="/public", tags=["public"])


def _lead_out(db: Session, lead) -> LeadOut:
    payload = LeadOut.model_validate(lead)
    score = latest_lead_score(db, lead)
    if score is not None:
        payload.latest_score = LeadScoreOut.model_validate(score)
    return payload


@router.get("/forms/{token}", response_class=HTMLResponse)
def embeddable_form(token: str, request: Request, db: Annotated[Session, Depends(get_db)]) -> HTMLResponse:
    enforce_rate_limit(key=f"public-form:{request.client.host if request.client else 'unknown'}", limit=60, window_seconds=60)
    resolve_form_key(db, token)
    endpoint = json.dumps(f"{str(request.base_url).rstrip('/')}/api/v1/public/forms/{token}/capture")
    query = request.query_params
    hidden = {
        "source": query.get("source") or "public_form",
        "channel": query.get("channel") or "website",
        "campaign": query.get("campaign") or "",
        "utm_source": query.get("utm_source") or query.get("channel") or "",
        "utm_medium": query.get("utm_medium") or "social",
        "utm_campaign": query.get("utm_campaign") or query.get("campaign") or "",
        "ad_id": query.get("ad_id") or "",
    }
    hidden_html = "".join(
        f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value)}">' for key, value in hidden.items()
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Tell us what you need</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0d1118;color:#eef2fa;margin:0}}
main{{max-width:32rem;margin:0 auto;padding:2rem 1.25rem 3rem}}
h1{{font-size:1.6rem;margin:0 0 .5rem}}
p{{line-height:1.5}}
label{{display:block;margin:1rem 0 .35rem}}
input,textarea{{width:100%;box-sizing:border-box;padding:.7rem;border:1px solid #293346;border-radius:8px;background:#101722;color:#eef2fa}}
button{{margin-top:1.25rem;width:100%;padding:.8rem;border:0;border-radius:8px;background:#99a5ff;color:#101722;font-weight:650}}
.row{{display:flex;gap:.75rem}}
.row label{{flex:1}}
.check{{display:flex;gap:.6rem;align-items:flex-start}}
.check input{{width:auto;margin-top:.2rem}}
#status{{min-height:1.4rem}}
</style></head><body><main>
<h1>Tell us what you need</h1>
<p>Share a few details and what you want. If the request is eligible, it becomes a lead for the team to continue.</p>
<form id="agrayian-form">
{hidden_html}
<div class="row"><label>First name<input name="first_name" required autocomplete="given-name"></label><label>Last name<input name="last_name" required autocomplete="family-name"></label></div>
<label>Work email<input name="email" type="email" required autocomplete="email"></label>
<label>Phone<input name="phone" type="tel" autocomplete="tel"></label>
<label>Company<input name="company_name" autocomplete="organization"></label>
<label>Role<input name="title" autocomplete="organization-title"></label>
<label>What do you want?<textarea name="request_note" required rows="5" placeholder="Describe the product or service you are interested in, and what you want next."></textarea></label>
<label class="check"><input type="checkbox" name="consent_email" value="true" required> I am interested and agree to be contacted about this request.</label>
<button type="submit">Send my interest</button>
<p id="status"></p>
</form>
<p>A name, email, description, and permission to be contacted are required before this becomes a lead.</p>
</main>
<script>
document.getElementById("agrayian-form").addEventListener("submit", async (event) => {{
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target).entries());
  data.consent_email = data.consent_email === "true";
  const response = await fetch({endpoint}, {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(data)
  }});
  const body = await response.json().catch(() => ({{}}));
  const payload = body.data || {{}};
  const status = document.getElementById("status");
  if (response.ok && payload.lead) status.textContent = "Thank you. Your interest is with the team.";
  else if (response.ok && payload.capture && payload.capture.status === "duplicate_review") status.textContent = "We already have this email. The team will review it.";
  else if (response.ok) status.textContent = "We saved this for review. A name, email, what you want, and permission to be contacted are required before it becomes a lead.";
  else status.textContent = "Could not submit.";
}});
</script>
</body></html>"""
    return HTMLResponse(page)


@router.post("/forms/{token}/capture", response_model=Envelope[CaptureResult])
def public_capture(
    token: str,
    body: CaptureIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[CaptureResult]:
    enforce_rate_limit(
        key=f"public-capture:{token}:{request.client.host if request.client else 'unknown'}",
        limit=20,
        window_seconds=60,
    )
    key = resolve_form_key(db, token)
    set_tenant_context(db, key.tenant_id)
    actor = db.scalar(select(User).where(User.tenant_id == key.tenant_id, User.is_active.is_(True)))
    if actor is None:
        raise HTTPException(status_code=409, detail="Tenant has no active user")
    payload = body.model_dump()
    payload["source"] = payload.get("source") or "public_form"
    payload["channel"] = payload.get("channel") or "website"
    if not interest_is_eligible(payload):
        capture_row = hold_interest(db, tenant_id=key.tenant_id, actor_id=actor.id, payload=payload)
        db.commit()
        db.refresh(capture_row)
        return Envelope(
            data=CaptureResult(
                capture=CaptureOut.model_validate(capture_row),
                lead=None,
                reviews_opened=0,
            )
        )
    capture_row, lead, reviews = capture_inbound(
        db,
        tenant_id=key.tenant_id,
        actor_id=actor.id,
        payload=payload,
    )
    process_pending_events(db, tenant_id=key.tenant_id, actor_id=actor.id)
    db.commit()
    db.refresh(capture_row)
    if lead is not None:
        db.refresh(lead)
    return Envelope(
        data=CaptureResult(
            capture=CaptureOut.model_validate(capture_row),
            lead=_lead_out(db, lead) if lead is not None else None,
            reviews_opened=len(reviews),
        )
    )
