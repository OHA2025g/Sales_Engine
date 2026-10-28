"""One product acknowledgement for a consented enquiry.

The legacy sequence does not send this message. A missing mailbox or grant
waits. A sent acknowledgement is not sent again.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import AIApproval
from app.models.assessment import AssessmentDecision, AssessmentEvidence
from app.models.autonomy import AutomationIdempotencyKey, AutonomousRun, AutonomousRunStep, AutopilotSettings
from app.models.crm import Lead
from app.providers.email import get_email_provider
from app.services.assessment import latest_decision
from app.services.automation_state import upsert_state
from app.services.demo_guard import external_execution_block
from app.services.email_send import execute_email_send
from app.services.grants import send_authorization
from app.services.operations import connected_mailbox_address
from app.services.product_context import context_for_lead

CONTENT_VERSION = "ack-v2"
_PRICE_WORDS = ("price", "pricing", "cost", "quote", "how much", "fee", "inr", "rupee", "₹")
ASKS = {
    "industry": "What industry is the company in?",
    "employees": "About how many people work there?",
    "persona": "What is your role?",
    "business_need": "What should we help with?",
}


def prepare_acknowledgement(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    settings: AutopilotSettings,
    run: AutonomousRun | None,
) -> dict:
    decision = latest_decision(db, tenant_id=tenant_id, lead_id=lead.id)
    if lead.source == "ai_discovery" or decision is None or not decision.response_eligible or decision.not_a_fit:
        return {"status": "skipped", "reason": "not_response_eligible"}
    if lead.opt_out or not lead.consent_email:
        return {"status": "skipped", "reason": "consent"}
    mailbox = connected_mailbox_address(db, tenant_id).casefold()
    if mailbox and (lead.email or "").strip().casefold() == mailbox:
        return {"status": "skipped", "reason": "self_reply"}
    questions = _unasked(db, tenant_id, lead, decision)
    version = CONTENT_VERSION + ":" + ",".join(questions)
    key = f"email.acknowledge:{lead.id}:{version}"
    existing = db.scalar(
        select(AIApproval).where(
            AIApproval.tenant_id == tenant_id,
            AIApproval.idempotency_key == key,
            AIApproval.deleted_at.is_(None),
        )
    )
    if existing is not None and existing.status == "approved":
        return {"status": "already_sent", "approval_id": str(existing.id), "waiting_reason": ""}
    body = _body(db, tenant_id, lead, questions)
    provider = get_email_provider(db, tenant_id)
    health = provider.health()
    approval = existing or _approval(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        lead=lead,
        run=run,
        key=key,
        body=body,
        version=version,
    )
    if not health.connected:
        _wait(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            lead=lead,
            run=run,
            state="WAITING_FOR_CONFIGURATION",
            next_action="connect_mailbox",
            reason=health.reason,
        )
        return {"status": "waiting_for_configuration", "approval_id": str(approval.id), "waiting_reason": health.reason}
    scope_block = external_execution_block(
        db,
        tenant_id=tenant_id,
        action="email.acknowledge",
        recipient=lead.email or "",
    )
    if scope_block:
        _wait(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            lead=lead,
            run=run,
            state="WAITING_FOR_AUTHORIZATION",
            next_action="authorize_demonstration",
            reason=scope_block,
        )
        return {
            "status": "waiting_for_authorization",
            "approval_id": str(approval.id),
            "waiting_reason": scope_block,
        }
    auth = send_authorization(db, tenant_id=tenant_id, settings=settings, action_type="email.acknowledge")
    if auth == "blocked":
        _wait(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            lead=lead,
            run=run,
            state="WAITING_FOR_AUTHORIZATION",
            next_action="configure_grant",
            reason="An inbound email grant is required before the acknowledgement can send.",
        )
        return {
            "status": "waiting_for_authorization",
            "approval_id": str(approval.id),
            "waiting_reason": "An inbound email grant is required before the acknowledgement can send.",
        }
    if auth == "approval":
        _wait(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            lead=lead,
            run=run,
            state="OUTREACH_APPROVAL_PENDING",
            next_action="approve_acknowledgement",
            reason="",
        )
        return {"status": "waiting_for_approval", "approval_id": str(approval.id), "waiting_reason": ""}
    approval.status = "approved"
    note = execute_email_send(db, tenant_id=tenant_id, actor_id=actor_id, approval=approval)
    approval.decision_note = note
    if note.startswith("Provider") and "recorded send" in note:
        _remember_questions(db, tenant_id=tenant_id, actor_id=actor_id, lead=lead, questions=questions)
    if "unknown" in note.casefold():
        return {"status": "unknown", "approval_id": str(approval.id), "waiting_reason": note}
    if note.startswith("Provider") and "recorded send" in note:
        _wait(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            lead=lead,
            run=run,
            state="CONTACTED",
            next_action="wait_for_reply",
            reason="",
        )
        return {"status": "sent", "approval_id": str(approval.id), "waiting_reason": "", "detail": note}
    if "BLOCKED BY CONFIGURATION" in note or "configuration" in note.casefold():
        _wait(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            lead=lead,
            run=run,
            state="WAITING_FOR_CONFIGURATION",
            next_action="connect_mailbox",
            reason=note,
        )
        return {"status": "waiting_for_configuration", "approval_id": str(approval.id), "waiting_reason": note}
    return {"status": "waiting", "approval_id": str(approval.id), "waiting_reason": note, "detail": note}


def continue_corrected_journey(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    run: AutonomousRun,
    settings: AutopilotSettings,
    idempotency_key: str,
) -> dict:
    stored_key = _continue_key(run.id, idempotency_key)
    existing = db.scalar(
        select(AutomationIdempotencyKey).where(
            AutomationIdempotencyKey.tenant_id == tenant_id,
            AutomationIdempotencyKey.key == stored_key,
            AutomationIdempotencyKey.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return {
            "journey_id": str(run.id),
            "job_id": existing.result_ref,
            "status": existing.window or run.status,
            "detail": "Replayed.",
        }
    if run.cancelled_at is not None or run.status == "cancelled":
        result = {"journey_id": str(run.id), "job_id": "", "status": "cancelled", "detail": "A cancelled journey cannot continue."}
        _remember_continue(db, tenant_id=tenant_id, actor_id=actor_id, run=run, stored_key=stored_key, result=result)
        return result
    lead = _lead_for_run(db, tenant_id, run)
    if lead is None:
        result = {"journey_id": str(run.id), "job_id": "", "status": run.status, "detail": "This journey has no lead."}
        _remember_continue(db, tenant_id=tenant_id, actor_id=actor_id, run=run, stored_key=stored_key, result=result)
        return result
    result = prepare_acknowledgement(db, tenant_id=tenant_id, actor_id=actor_id, lead=lead, settings=settings, run=run)
    payload = {
        "journey_id": str(run.id),
        "job_id": str(result.get("approval_id") or run.id),
        "status": str(result.get("status") or run.status),
        "detail": str(result.get("waiting_reason") or result.get("detail") or ""),
    }
    _remember_continue(db, tenant_id=tenant_id, actor_id=actor_id, run=run, stored_key=stored_key, result=payload)
    return payload


def _continue_key(run_id: UUID, idempotency_key: str) -> str:
    raw = f"journey:continue:{run_id}:{idempotency_key}"
    if len(raw) <= 240:
        return raw
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    return f"journey:continue:{run_id}:{digest}"


def _remember_continue(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    run: AutonomousRun,
    stored_key: str,
    result: dict,
) -> None:
    db.add(
        AutomationIdempotencyKey(
            tenant_id=tenant_id,
            created_by=actor_id,
            key=stored_key,
            workflow="journey_continue",
            entity_id=str(run.id),
            action_type="continue",
            window=str(result.get("status") or "")[:40],
            result_ref=str(result.get("job_id") or "")[:64],
        )
    )
    db.flush()


def _lead_for_run(db: Session, tenant_id: UUID, run: AutonomousRun) -> Lead | None:
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
    if step is None or not step.entity_id:
        return None
    try:
        lead_id = UUID(step.entity_id)
    except ValueError:
        return None
    return db.scalar(select(Lead).where(Lead.tenant_id == tenant_id, Lead.id == lead_id, Lead.deleted_at.is_(None)))


def _unasked(db: Session, tenant_id: UUID, lead: Lead, decision: AssessmentDecision) -> list[str]:
    try:
        payload = json.loads(decision.fit_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    facts = {row.get("facet"): row for row in payload.get("facts") or [] if isinstance(row, dict)}
    person_id = str(lead.contact_id or lead.id)
    pending: list[str] = []
    for facet in ASKS:
        fact = facts.get(facet) or {}
        if fact.get("fact_class") not in {None, "", "unknown"}:
            continue
        asked = db.scalar(
            select(AssessmentEvidence.id).where(
                AssessmentEvidence.tenant_id == tenant_id,
                AssessmentEvidence.person_id == person_id,
                AssessmentEvidence.kind == f"clarification:{facet}",
                AssessmentEvidence.source == "acknowledgement",
                AssessmentEvidence.deleted_at.is_(None),
            )
        )
        if asked is None:
            pending.append(facet)
    return pending


def _price_requested(note: str) -> bool:
    folded = note.casefold()
    return any(word in folded for word in _PRICE_WORDS)


def _body(db: Session, tenant_id: UUID, lead: Lead, questions: list[str]) -> str:
    context = context_for_lead(db, tenant_id, lead)
    name = context.customer_facing_name
    if context.company_name and name:
        lines = [f"Thanks for contacting {context.company_name} about {name}. We received your enquiry."]
    elif name:
        lines = [f"Thanks for contacting us about {name}. We received your enquiry."]
    else:
        lines = ["Thanks for your enquiry. We received it."]
    note = (lead.notes or "").strip()
    if note:
        lines.append(f"You wrote: {note[:500]}")
    if note and _price_requested(note):
        price = context.price_line()
        if price:
            lines.append(price)
    relevant = [facet for facet in questions if not (facet == "business_need" and note)]
    if relevant:
        lines.append("")
        lines.extend(ASKS[facet] for facet in relevant)
    return "\n".join(lines)


def _approval(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    run: AutonomousRun | None,
    key: str,
    body: str,
    version: str,
) -> AIApproval:
    approval = AIApproval(
        tenant_id=tenant_id,
        created_by=actor_id,
        action_level=2,
        action_type="email.acknowledge",
        title=f"Acknowledge {lead.email or lead.id}",
        payload_json=json.dumps(
            {
                "lead_id": str(lead.id),
                "subject": "We received your enquiry",
                "body": body,
                "purpose": "acknowledgement",
                "content_version": version,
                "why": "Consented enquiry. Missing firmographics do not block this acknowledgement.",
            }
        ),
        status="pending",
        run_id=run.id if run is not None else None,
        entity_type="lead",
        entity_id=str(lead.id),
        idempotency_key=key,
    )
    db.add(approval)
    db.flush()
    return approval


def _remember_questions(db: Session, *, tenant_id: UUID, actor_id: UUID, lead: Lead, questions: list[str]) -> None:
    from datetime import UTC, datetime

    person_id = str(lead.contact_id or lead.id)
    now = datetime.now(UTC)
    for facet in questions:
        db.add(
            AssessmentEvidence(
                tenant_id=tenant_id,
                created_by=actor_id,
                person_id=person_id,
                kind=f"clarification:{facet}",
                source="acknowledgement",
                content_hash=facet,
                polarity="neutral",
                observed_at=now,
                excerpt=ASKS[facet],
            )
        )
    db.flush()


def _wait(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    run: AutonomousRun | None,
    state: str,
    next_action: str,
    reason: str,
) -> None:
    upsert_state(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        state=state,
        last_action="acknowledge",
        next_action=next_action,
        blocked_reason=reason,
        run_id=run.id if run is not None else None,
    )
