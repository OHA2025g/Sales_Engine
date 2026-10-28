from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.autonomy import AutopilotSettings
from app.models.crm import Lead, LeadScore, Task
from app.models.identity import DomainEvent
from app.services.assessment import Fact, assess_and_store, handoff_sales_opportunity
from app.services.audit import emit_event
from app.services.crm import add_activity


def latest_score(db: Session, lead: Lead) -> LeadScore | None:
    return db.scalar(
        select(LeadScore)
        .where(LeadScore.lead_id == lead.id, LeadScore.deleted_at.is_(None))
        .order_by(LeadScore.created_at.desc())
    )


def qualify_lead(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    settings: AutopilotSettings,
    correlation_id: str = "",
    meeting_requested: bool = False,
    fact_overrides: list[Fact] | None = None,
) -> dict:
    score = latest_score(db, lead)
    reasons: list[str] = []
    missing: list[str] = []
    total = score.total if score else 0
    icp_fit = score.icp_fit if score else 0
    if score is None:
        missing.append("score")
        reasons.append("No persisted rules-v1 score")
    elif total < settings.minimum_lead_score:
        reasons.append(f"Score {total} is below minimum {settings.minimum_lead_score}")
    else:
        reasons.append(f"Score {total} meets minimum {settings.minimum_lead_score}")
    if not lead.email and not lead.company_name:
        missing.append("identity")
        reasons.append("Lead has no email or company")
    if lead.intent_score < settings.minimum_intent_score:
        reasons.append(f"Intent {lead.intent_score} is below minimum {settings.minimum_intent_score}")
    decision = assess_and_store(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        lead=lead,
        settings=settings,
        meeting_requested=meeting_requested,
        overrides=fact_overrides,
        correlation_id=correlation_id,
    )
    outbound_eligible = bool(decision["outbound_eligible"])
    if outbound_eligible:
        sequence_ready = True
        reasons.append("Assessment permits outbound. The numerical score is recorded and does not veto.")
    else:
        sequence_ready = False
        reasons.append("Assessment does not permit outbound.")
    sales_qualified = bool(decision["sales_qualified"])
    held = bool(decision["response_eligible"] or decision["meeting_eligible"])
    if sales_qualified:
        handed = handoff_sales_opportunity(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            lead=lead,
            correlation_id=correlation_id,
            decision_id=str(decision.get("decision_id") or ""),
        )
        if handed is None and lead.account_id is None:
            _ensure_handoff_task(db, tenant_id=tenant_id, actor_id=actor_id, lead=lead)
        if not _already_emitted(db, tenant_id, "lead.sales_qualified", str(lead.id)):
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="lead.sales_qualified",
                entity_type="lead",
                entity_id=str(lead.id),
                payload={"decision_id": decision.get("decision_id"), "policy": "heuristics-v2"},
                correlation_id=correlation_id,
            )
    qualified = sequence_ready or sales_qualified
    if qualified and lead.status == "new":
        lead.status = "working"
    if sales_qualified or sequence_ready:
        event_type = "lead.qualified"
    elif decision["not_a_fit"] or lead.opt_out:
        event_type = "lead.disqualified"
    else:
        event_type = "assessment.updated"
    reasons.extend(decision["reasons"])
    payload = {
        "qualified": qualified,
        "total": total,
        "icp_fit": icp_fit,
        "reasons": reasons,
        "missing": missing,
        "policy": "rules-v1",
        "response_eligible": decision["response_eligible"],
        "outbound_eligible": outbound_eligible,
        "meeting_eligible": decision["meeting_eligible"],
        "sales_qualified": sales_qualified,
        "not_a_fit": decision["not_a_fit"],
        "next_action": decision["next_action"],
        "coverage_known": decision["coverage_known"],
        "coverage_required": decision["coverage_required"],
        "confidence": decision["confidence"],
        "held_for_response": held and not qualified,
        "decision_id": decision.get("decision_id"),
    }
    title = "Lead qualified" if qualified else "Lead held for a response" if held else "Lead not qualified"
    add_activity(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        activity_type="qualification",
        title=title,
        body=" | ".join(reasons),
        actor_type="ai",
    )
    if event_type != "assessment.updated" or not _already_emitted(db, tenant_id, event_type, str(lead.id)):
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type=event_type,
            entity_type="lead",
            entity_id=str(lead.id),
            payload=payload,
            correlation_id=correlation_id,
        )
    return payload


def _ensure_handoff_task(db: Session, *, tenant_id: UUID, actor_id: UUID, lead: Lead) -> None:
    title = "Resolve the account before sales handoff"
    existing = db.scalar(
        select(Task).where(
            Task.tenant_id == tenant_id,
            Task.entity_type == "lead",
            Task.entity_id == str(lead.id),
            Task.title == title,
            Task.status == "open",
            Task.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return
    db.add(
        Task(
            tenant_id=tenant_id,
            created_by=actor_id,
            title=title,
            description="Sales qualification passed. The opportunity waits until this lead has an account.",
            status="open",
            priority="high",
            owner_id=lead.owner_id or actor_id,
            entity_type="lead",
            entity_id=str(lead.id),
            source="automation",
        )
    )
    db.flush()


def _already_emitted(db: Session, tenant_id: UUID, event_type: str, entity_id: str) -> bool:
    return (
        db.scalar(
            select(DomainEvent.id).where(
                DomainEvent.tenant_id == tenant_id,
                DomainEvent.event_type == event_type,
                DomainEvent.entity_id == entity_id,
            )
        )
        is not None
    )
