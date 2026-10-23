"""Operational truth for the Command Centre. Counts come from stored rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.assessment import AssessmentEvidence
from app.models.autonomy import AutonomousRun, AutonomousRunStep, AutopilotSettings
from app.models.crm import Lead
from app.models.execution import RevenueObjective
from app.models.funnel import PublicFormKey
from app.models.identity import DomainEvent
from app.models.integrations import EmailMessage, ProviderAccount
from app.models.lifecycle import MeetingRecord, Product
from app.providers.calendar import get_calendar_provider
from app.providers.email import get_email_provider
from app.services.automation_state import get_state
from app.services.discovery import discovery_board
from app.services.marketing import marketing_board
from app.services.public_forms import form_key_url
from app.services.scheduler_health import beat_status


def _scheduler(beat: dict) -> dict:
    stamped = beat.get("last_beat_at")
    if stamped is not None and not isinstance(stamped, str):
        beat = dict(beat)
        beat["last_beat_at"] = stamped.isoformat()
    return beat


def _age_seconds(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    stamped = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return max(int((now - stamped).total_seconds()), 0)


def operations_view(db: Session, tenant_id: UUID) -> dict:
    now = datetime.now(UTC)
    objective = db.scalar(
        select(RevenueObjective)
        .where(
            RevenueObjective.tenant_id == tenant_id,
            RevenueObjective.deleted_at.is_(None),
            RevenueObjective.status.in_(["active", "approved"]),
        )
        .order_by(RevenueObjective.created_at.desc())
    )
    product = db.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.deleted_at.is_(None)).order_by(Product.created_at.asc())
    )
    settings = db.scalar(select(AutopilotSettings).where(AutopilotSettings.tenant_id == tenant_id, AutopilotSettings.deleted_at.is_(None)))
    offer = None
    if objective is not None or product is not None:
        offer = {
            "name": objective.name if objective is not None else product.name,
            "offer_key": objective.offer_key if objective is not None else "",
            "scope": objective.segment if objective is not None else "",
            "sales_rules_configured": bool(settings and (settings.sales_rules_json or "").strip() not in {"", "{}"}),
        }
    runs = db.scalars(
        select(AutonomousRun)
        .where(AutonomousRun.tenant_id == tenant_id, AutonomousRun.deleted_at.is_(None))
        .order_by(AutonomousRun.created_at.desc())
        .limit(12)
    ).all()
    journeys = []
    for run in runs:
        step = db.scalar(
            select(AutonomousRunStep)
            .where(
                AutonomousRunStep.tenant_id == tenant_id,
                AutonomousRunStep.run_id == run.id,
                AutonomousRunStep.entity_type == "lead",
                AutonomousRunStep.deleted_at.is_(None),
            )
            .order_by(AutonomousRunStep.position.asc())
        )
        lead = None
        state = None
        if step is not None and step.entity_id:
            try:
                lead = db.get(Lead, UUID(step.entity_id))
            except ValueError:
                lead = None
            if lead is not None and lead.tenant_id == tenant_id:
                state = get_state(db, tenant_id=tenant_id, entity_type="lead", entity_id=str(lead.id))
        journeys.append(
            {
                "journey_id": str(run.id),
                "status": run.status,
                "business_state": run.business_state,
                "workflow": run.workflow,
                "summary": run.summary,
                "lead_id": str(lead.id) if lead is not None else "",
                "lead_email": lead.email if lead is not None else "",
                "next_action": state.next_action if state is not None else "",
                "waiting_reason": state.blocked_reason if state is not None else "",
            }
        )
    running = db.scalars(
        select(AutonomousRunStep)
        .where(
            AutonomousRunStep.tenant_id == tenant_id,
            AutonomousRunStep.status == "running",
            AutonomousRunStep.deleted_at.is_(None),
        )
        .order_by(AutonomousRunStep.started_at.asc())
        .limit(20)
    ).all()
    running_steps = []
    stale = []
    for step in running:
        age = _age_seconds(step.started_at, now)
        expired = False
        if step.lease_until is not None:
            lease_end = step.lease_until if step.lease_until.tzinfo else step.lease_until.replace(tzinfo=UTC)
            expired = lease_end < now
        row = {
            "step_id": str(step.id),
            "journey_id": str(step.run_id),
            "name": step.name,
            "lease_owner": step.lease_owner,
            "lease_until": step.lease_until.isoformat() if step.lease_until else "",
            "age_seconds": age,
            "stale": expired,
        }
        running_steps.append(row)
        if expired:
            stale.append(row)
    oldest_pending = db.scalar(
        select(func.min(DomainEvent.created_at)).where(
            DomainEvent.tenant_id == tenant_id,
            DomainEvent.delivery_status == "pending",
        )
    )
    messages = db.scalars(
        select(EmailMessage)
        .where(EmailMessage.tenant_id == tenant_id, EmailMessage.deleted_at.is_(None))
        .order_by(EmailMessage.created_at.desc())
        .limit(8)
    ).all()
    meetings = db.scalars(
        select(MeetingRecord)
        .where(MeetingRecord.tenant_id == tenant_id, MeetingRecord.deleted_at.is_(None))
        .order_by(MeetingRecord.created_at.desc())
        .limit(8)
    ).all()
    evidence_rows = db.scalars(
        select(AssessmentEvidence)
        .where(AssessmentEvidence.tenant_id == tenant_id, AssessmentEvidence.deleted_at.is_(None))
        .order_by(AssessmentEvidence.observed_at.desc())
        .limit(8)
    ).all()
    evidence = [
        {
            "kind": "email",
            "status": row.status,
            "provider": row.provider,
            "provider_ref": row.provider_message_id,
            "excerpt": (row.subject or "")[:160],
        }
        for row in messages
    ]
    evidence.extend(
        {
            "kind": "meeting",
            "status": row.status,
            "provider": row.provider,
            "provider_ref": row.provider_event_id or "",
            "excerpt": row.title,
        }
        for row in meetings
    )
    evidence.extend(
        {"kind": row.kind, "status": row.source, "provider": "", "provider_ref": "", "excerpt": (row.excerpt or "")[:160]}
        for row in evidence_rows
    )
    def _count(event_type: str) -> int:
        return int(
            db.scalar(
                select(func.count()).select_from(DomainEvent).where(
                    DomainEvent.tenant_id == tenant_id,
                    DomainEvent.event_type == event_type,
                )
            )
            or 0
        )

    exceptions = [
        {
            "journey_id": row["journey_id"],
            "status": row["status"],
            "waiting_reason": row["waiting_reason"] or row["summary"],
            "next_action": row["next_action"],
        }
        for row in journeys
        if row["status"] in {"blocked", "waiting_for_configuration", "waiting_for_authorization", "WAITING_FOR_APPROVAL"}
        or row["waiting_reason"]
    ]
    return {
        "offer": offer,
        "journeys": journeys,
        "running_steps": running_steps,
        "stale_leases": stale,
        "queue_age_seconds": _age_seconds(oldest_pending, now),
        "scheduler": _scheduler(beat_status(db, stale_after=timedelta(minutes=3))),
        "worker": _scheduler(beat_status(db, key="celery_worker", stale_after=timedelta(seconds=90))),
        "held_external_work": int(
            db.scalar(
                select(func.count()).select_from(DomainEvent).where(
                    DomainEvent.tenant_id == tenant_id,
                    DomainEvent.delivery_status == "held",
                )
            )
            or 0
        ),
        "evidence": evidence[:16],
        "exceptions": exceptions[:8],
        "outcomes": {
            "enquiries": _count("enquiry.received"),
            "responses_sent": _count("response.sent"),
            "meetings_booked": _count("meeting.booked"),
            "sales_qualified": _count("lead.sales_qualified"),
            "opportunities_created": _count("opportunity.created"),
        },
        "discovery": _discovery_board(db, tenant_id),
        "marketing": _marketing_board(db, tenant_id),
    }


def journey_next_action(db: Session, *, tenant_id: UUID, run: AutonomousRun) -> dict:
    from app.services.assessment import latest_decision

    step = db.scalar(
        select(AutonomousRunStep)
        .where(
            AutonomousRunStep.tenant_id == tenant_id,
            AutonomousRunStep.run_id == run.id,
            AutonomousRunStep.entity_type == "lead",
            AutonomousRunStep.deleted_at.is_(None),
        )
        .order_by(AutonomousRunStep.position.asc())
    )
    decision = None
    state = None
    if step is not None and step.entity_id:
        try:
            lead_id = UUID(step.entity_id)
        except ValueError:
            lead_id = None
        if lead_id is not None:
            decision = latest_decision(db, tenant_id=tenant_id, lead_id=lead_id)
            state = get_state(db, tenant_id=tenant_id, entity_type="lead", entity_id=str(lead_id))
    return {
        "journey_id": run.id,
        "job_id": str(run.id),
        "state": run.status,
        "next_action": (state.next_action if state is not None and state.next_action else (decision.next_action if decision is not None else "")),
        "waiting_reason": state.blocked_reason if state is not None else "",
        "coverage_known": decision.coverage_known if decision is not None else 0,
        "coverage_required": decision.coverage_required if decision is not None else 0,
        "confidence": decision.confidence if decision is not None else "none",
        "meeting_eligible": bool(decision.meeting_eligible) if decision is not None else False,
        "sales_qualified": bool(decision.sales_qualified) if decision is not None else False,
    }


def _localhost(value: str) -> bool:
    folded = value.casefold()
    return "localhost" in folded or "127.0.0.1" in folded


def connected_mailbox_address(db: Session, tenant_id: UUID) -> str:
    row = db.scalar(
        select(ProviderAccount)
        .where(
            ProviderAccount.tenant_id == tenant_id,
            ProviderAccount.provider.in_(("google", "gmail")),
            ProviderAccount.status == "connected",
            ProviderAccount.deleted_at.is_(None),
        )
        .order_by(ProviderAccount.created_at.desc())
    )
    if row is None:
        return ""
    return (row.provider_account_id or "").strip()


def _capability_verified(db: Session, tenant_id: UUID, providers: tuple[str, ...]) -> bool:
    row = db.scalar(
        select(ProviderAccount)
        .where(
            ProviderAccount.tenant_id == tenant_id,
            ProviderAccount.provider.in_(providers),
            ProviderAccount.status == "connected",
            ProviderAccount.deleted_at.is_(None),
            ProviderAccount.last_success_at.is_not(None),
        )
        .order_by(ProviderAccount.created_at.desc())
    )
    address = (row.provider_account_id or "").strip() if row is not None else ""
    return "@" in address and "mock" not in address.casefold()


def _provider_level(health: object, *, verified: bool) -> tuple[str, str]:
    reason = str(getattr(health, "reason", "") or "")
    if bool(getattr(health, "is_mock", False)):
        return "fixture", f"Mock functionality is ready for fixtures. This is not a verified live mailbox. {reason}".strip()
    if not bool(getattr(health, "connected", False)):
        return "blocked", reason or "The provider is not configured."
    if verified:
        return "verified", reason or "A successful provider call is recorded for this mailbox."
    return "configured", f"Provider credentials are configured. Capability has not been verified. {reason}".strip()


def _discovery_board(db: Session, tenant_id: UUID) -> dict:
    return discovery_board(db, tenant_id)


def _marketing_board(db: Session, tenant_id: UUID) -> dict:
    return marketing_board(db, tenant_id)


def channel_readiness(db: Session, *, tenant_id: UUID, channel: str) -> dict:
    settings = get_settings()
    rows: list[dict] = []
    origin = settings.web_app_origin.strip()
    rows.append(
        {
            "name": "operator_app",
            "status": "ready" if origin else "blocked",
            "reason": "The operator app origin is set." if origin else "WEB_APP_ORIGIN is empty.",
            "href": origin,
        }
    )
    form = db.scalar(
        select(PublicFormKey)
        .where(PublicFormKey.tenant_id == tenant_id, PublicFormKey.status == "active", PublicFormKey.deleted_at.is_(None))
        .order_by(PublicFormKey.created_at.desc())
    )
    form_url = form_key_url(form) if form is not None else ""
    if not form_url:
        rows.append({"name": "capture_form", "status": "blocked", "reason": "No active capture form exists for this tenant.", "href": ""})
    elif _localhost(form_url):
        rows.append(
            {
                "name": "capture_form",
                "status": "blocked",
                "reason": "The form URL is on localhost. A buyer who is not on this computer cannot open it. It is usable by the operator on this machine.",
                "href": form_url,
            }
        )
    else:
        rows.append({"name": "capture_form", "status": "ready", "reason": "The capture form URL is not localhost.", "href": form_url})
    selected = (channel or "email").casefold()
    mailbox_level = "not_required"
    if selected in {"email", "inbound"}:
        health = get_email_provider(db, tenant_id).health()
        mailbox_level, mailbox_reason = _provider_level(
            health, verified=_capability_verified(db, tenant_id, ("google", "gmail"))
        )
        rows.append({"name": "mailbox", "status": mailbox_level, "reason": mailbox_reason, "href": ""})
    elif selected == "calendar":
        health = get_calendar_provider(db, tenant_id).health()
        mailbox_level, mailbox_reason = _provider_level(
            health, verified=_capability_verified(db, tenant_id, ("google_calendar", "calendar"))
        )
        rows.append({"name": "calendar", "status": mailbox_level, "reason": mailbox_reason, "href": ""})
    else:
        rows.append({"name": selected, "status": "not_required", "reason": "This channel has no provider check in the inbound journey.", "href": ""})
    callback = settings.public_api_base_url.strip()
    if selected in {"email", "inbound"}:
        if _localhost(callback):
            rows.append(
                {
                    "name": "provider_callbacks",
                    "status": "blocked",
                    "reason": "Provider callbacks need a public HTTPS URL. Localhost can send a fixture acknowledgement, and it cannot receive Gmail push.",
                    "href": "",
                }
            )
        else:
            rows.append({"name": "provider_callbacks", "status": "ready", "reason": "PUBLIC_API_BASE_URL is not localhost.", "href": ""})
    else:
        rows.append({"name": "provider_callbacks", "status": "not_required", "reason": "This channel does not need a callback for the inbound journey.", "href": ""})
    form_ready = any(row["name"] == "capture_form" and row["status"] == "ready" for row in rows)
    callbacks_ready = any(row["name"] == "provider_callbacks" and row["status"] == "ready" for row in rows)
    live_ok = mailbox_level == "verified" and form_ready and callbacks_ready
    if mailbox_level == "fixture":
        live_reason = "A mock mailbox cannot be used for the controlled live demonstration."
    elif mailbox_level != "verified":
        live_reason = "The provider is not capability-verified, so the live demonstration is not eligible."
    elif not form_ready or not callbacks_ready:
        live_reason = "The mailbox is verified, and the public form or callback URL is still local."
    else:
        live_reason = "The mailbox is capability-verified and the public form and callback URL are not localhost."
    rows.append({"name": "live_demonstration", "status": "eligible" if live_ok else "blocked", "reason": live_reason, "href": ""})
    return {"channel": selected, "checks": rows, "eligible_for_live_demo": live_ok}
