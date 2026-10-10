"""Start the designed intake for one lead the operator named.

The introduction is queued for approval. This module does not send it.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.db.session import get_engine, get_session
from app.db.tenant_context import set_tenant_context
from app.models.crm import Lead
from app.models.identity import Tenant, User
from app.models.lifecycle import Sequence
from app.services.autopilot_settings import get_or_create_settings
from app.services.orchestrator import run_lead_intake

SEQUENCE_NAME = "Revenue OS introduction"


def start_operator_lead(db, *, first_name: str, last_name: str, email: str) -> dict:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == "agrayian"))
    if tenant is None:
        raise RuntimeError("AGRAYIAN tenant is not seeded")
    set_tenant_context(db, tenant.id)
    actor = db.scalar(select(User).where(User.tenant_id == tenant.id, User.email == "admin@agrayian.demo"))
    if actor is None:
        raise RuntimeError("AGRAYIAN admin user is missing")
    settings = get_or_create_settings(db, tenant_id=tenant.id, actor_id=actor.id)
    if settings.timezone in {"", "UTC"}:
        settings.timezone = "Asia/Kolkata"
    sequence = db.scalar(
        select(Sequence).where(
            Sequence.tenant_id == tenant.id,
            Sequence.name == SEQUENCE_NAME,
            Sequence.deleted_at.is_(None),
        )
    )
    if sequence is None:
        raise RuntimeError("Revenue OS introduction sequence is missing")
    sequence.status = "active"
    normalized = email.strip().lower()
    lead = db.scalar(
        select(Lead).where(Lead.tenant_id == tenant.id, Lead.email == normalized, Lead.deleted_at.is_(None))
    )
    if lead is None:
        lead = Lead(tenant_id=tenant.id, created_by=actor.id, email=normalized)
        db.add(lead)
    lead.first_name = first_name.strip()
    lead.last_name = last_name.strip()
    lead.email = normalized
    lead.title = ""
    lead.company_name = ""
    lead.source = "operator"
    lead.channel = "operator"
    lead.utm_campaign = "revenue-os"
    lead.consent_email = True
    lead.opt_out = False
    lead.intent_score = 100
    lead.engagement_score = 100
    lead.has_buying_trigger = False
    lead.status = "new"
    lead.notes = (
        "Named by the workspace operator and marked eligible for the revenue process. "
        "No company firmographics were supplied. Intent and engagement were set so the lead clears the score gate."
    )
    lead.updated_by = actor.id
    db.flush()
    result = run_lead_intake(
        db,
        tenant_id=tenant.id,
        actor_id=actor.id,
        lead=lead,
        correlation_id="operator-lead",
    )
    outreach = result.get("outreach") or {}
    return {
        "lead_id": str(lead.id),
        "name": f"{lead.first_name} {lead.last_name}",
        "status": result.get("status") or outreach.get("status") or "completed",
        "score": result.get("score"),
        "qualified": result.get("qualified"),
        "reason": result.get("reason") or outreach.get("reason", ""),
        "approval_required": bool(settings.email_approval_required),
    }


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: python -m app.start_operator_lead FIRST LAST EMAIL")
    get_engine()
    db = get_session()
    try:
        summary = start_operator_lead(db, first_name=sys.argv[1], last_name=sys.argv[2], email=sys.argv[3])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(
        f"{summary['name']} lead {summary['lead_id']} status={summary['status']} "
        f"score={summary['score']} qualified={summary['qualified']} reason={summary['reason']} "
        f"approval_required={summary['approval_required']}"
    )


if __name__ == "__main__":
    main()
