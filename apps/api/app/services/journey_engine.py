"""Activated journeys, step execution, and the inbound handoff."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import AIApproval
from app.models.crm import ICP, Account, Lead, Opportunity, Task
from app.models.execution import JourneyLink, SlaClock, StageEvidence
from app.models.lifecycle import MeetingRecord, Sequence, SequenceEnrollment, SequenceStep
from app.services.automation_state import get_state, upsert_state
from app.services.content import draft_email_from_facts
from app.services.crm import STAGE_PROBABILITY, add_activity

SUPPORTED_STEPS = {"email_draft", "email_send", "send", "wait", "task", "branch", "meeting"}
PROGRESS_STATES = {
    "DISCOVERED",
    "ENRICHING",
    "ENRICHED",
    "SCORING",
    "SCORED",
    "QUALIFYING",
    "QUALIFIED",
    "RESEARCHING",
    "READY_FOR_OUTREACH",
    "OUTREACH_APPROVAL_PENDING",
    "CONTACTED",
    "MEETING_SCHEDULED",
}


def evaluation_key(lead: Lead) -> str:
    raw = f"consent:{int(bool(lead.consent_email))}:opt:{int(bool(lead.opt_out))}:email:{lead.email}"
    if len(raw) <= 64:
        return raw
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def block_evaluation(db: Session, *, tenant_id: UUID, lead: Lead, blocked_reason: str) -> str:
    """Version the facts that caused a block so a real change resumes once."""
    from app.services.autopilot_settings import get_or_create_settings
    from app.services.grants import send_authorization
    from app.services.qualification import latest_score

    extra = blocked_reason or ""
    settings = get_or_create_settings(db, tenant_id=tenant_id)
    if extra in {"scoped_grant_required", "grant_required"}:
        extra = send_authorization(db, tenant_id=tenant_id, settings=settings, action_type="sequence.email.send")
    elif extra in {"no_sequence", "no_activated_sequence"}:
        sequence = select_activated_sequence(db, tenant_id, lead)
        extra = "none" if sequence is None else str(sequence.id)
    elif "score" in extra.lower():
        latest = latest_score(db, lead)
        total = latest.total if latest else 0
        extra = f"score:{total}:{settings.minimum_lead_score}"
    raw = f"{evaluation_key(lead)}|{extra}"
    if len(raw) <= 64:
        return raw
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def sequence_is_runnable(db: Session, sequence: Sequence) -> bool:
    if sequence.status not in {"live", "active"}:
        return False
    steps = db.scalars(
        select(SequenceStep).where(SequenceStep.sequence_id == sequence.id, SequenceStep.deleted_at.is_(None))
    ).all()
    if not steps:
        return False
    return all(step.action_type in SUPPORTED_STEPS for step in steps)


def select_activated_sequence(db: Session, tenant_id: UUID, lead: Lead | None = None) -> Sequence | None:
    rows = db.scalars(
        select(Sequence)
        .where(
            Sequence.tenant_id == tenant_id,
            Sequence.deleted_at.is_(None),
            Sequence.channel == "email",
            Sequence.status.in_(["live", "active"]),
        )
        .order_by(Sequence.routing_priority.desc(), Sequence.created_at.desc())
    ).all()
    for sequence in rows:
        if not sequence_is_runnable(db, sequence):
            continue
        if lead is None:
            return sequence
        if sequence.icp_id:
            icp = db.get(ICP, sequence.icp_id)
            account = db.get(Account, lead.account_id) if lead.account_id else None
            industries = {part.strip() for part in (icp.industries or "").split(",") if part.strip()} if icp else set()
            if icp is None:
                continue
            if account and industries and account.industry and account.industry not in industries:
                continue
        if sequence.campaign_id and lead.campaign_id and sequence.campaign_id != lead.campaign_id:
            continue
        if sequence.offer_key and sequence.offer_key not in {lead.campaign, lead.utm_campaign}:
            continue
        return sequence
    return None


def open_configuration_exception(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    reason: str,
    run_id: UUID | None = None,
) -> None:
    upsert_state(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        state="BLOCKED",
        last_action="configuration_exception",
        next_action="activate_sequence",
        blocked_reason=reason,
        run_id=run_id,
    )
    state = get_state(db, tenant_id=tenant_id, entity_type="lead", entity_id=str(lead.id))
    if state is not None:
        state.execution_status = "blocked"
        state.business_state = "assessed"
        state.resume_step = "outreach"
        state.evaluation_key = block_evaluation(db, tenant_id=tenant_id, lead=lead, blocked_reason=reason)
    if reason == "no_activated_sequence":
        db.add(
            Task(
                tenant_id=tenant_id,
                created_by=actor_id,
                title="Activate a journey for this lead",
                description=f"{lead.email or lead.id} has no activated sequence for its segment.",
                status="open",
                priority="medium",
                entity_type="lead",
                entity_id=str(lead.id),
                source="workflow",
            )
        )


def mark_execution(
    db: Session,
    *,
    tenant_id: UUID,
    entity_id: str,
    execution_status: str,
    business_state: str = "",
    resume_step: str = "",
    evaluation: str = "",
) -> None:
    state = get_state(db, tenant_id=tenant_id, entity_type="lead", entity_id=entity_id)
    if state is None:
        return
    state.execution_status = execution_status
    if business_state:
        state.business_state = business_state
    if resume_step:
        state.resume_step = resume_step
    if evaluation:
        state.evaluation_key = evaluation


def intake_should_resume(db: Session, *, tenant_id: UUID, lead: Lead, result_ref: str) -> bool:
    if not result_ref:
        return True
    state = get_state(db, tenant_id=tenant_id, entity_type="lead", entity_id=str(lead.id))
    if state is None:
        return False
    if state.state in {"BLOCKED", "PAUSED"} or state.execution_status in {"blocked", "paused", "failed"}:
        return state.evaluation_key != evaluation_key(lead) or state.resume_step != ""
    return state.state not in PROGRESS_STATES or state.state in {"DISCOVERED", "ENRICHING", "ENRICHED", "SCORING", "SCORED", "QUALIFYING"}


def progress_rank(state: str) -> int:
    order = list(PROGRESS_STATES)
    try:
        return order.index(state)
    except ValueError:
        return -1


def execute_due_step(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    enrollment: SequenceEnrollment,
    step: SequenceStep,
    lead: Lead,
) -> str:
    kind = step.action_type
    if kind not in SUPPORTED_STEPS:
        enrollment.status = "blocked"
        return "unsupported"
    if kind == "wait":
        due = enrollment.next_run_at or datetime.now(UTC)
        if due > datetime.now(UTC):
            return "waiting"
        _advance(db, enrollment, step)
        return "waited"
    if kind == "task":
        db.add(
            Task(
                tenant_id=tenant_id,
                created_by=actor_id,
                title=f"Sequence task: {step.template[:120] or 'Follow up'}",
                description=step.template,
                status="open",
                priority="medium",
                entity_type="lead",
                entity_id=str(lead.id),
                source="workflow",
            )
        )
        _advance(db, enrollment, step)
        return "task"
    if kind == "branch":
        try:
            rule = json.loads(step.template or "{}")
        except json.JSONDecodeError:
            rule = {}
        wants_consent = bool(rule.get("consent_email", True))
        if bool(lead.consent_email) != wants_consent:
            enrollment.status = "blocked"
            return "branch_blocked"
        _advance(db, enrollment, step)
        return "branched"
    if kind == "meeting":
        db.add(
            Task(
                tenant_id=tenant_id,
                created_by=actor_id,
                title=f"Prepare meeting for {lead.email or 'lead'}",
                description=step.template,
                status="open",
                priority="high",
                entity_type="lead",
                entity_id=str(lead.id),
                source="workflow",
            )
        )
        _advance(db, enrollment, step)
        return "meeting"
    key = f"sequence.email.send:{lead.id}:{enrollment.id}:{enrollment.current_step}"
    exists = db.scalar(
        select(AIApproval).where(
            AIApproval.tenant_id == tenant_id,
            AIApproval.idempotency_key == key,
            AIApproval.deleted_at.is_(None),
        )
    )
    if exists is None:
        db.add(
            AIApproval(
                tenant_id=tenant_id,
                created_by=actor_id,
                action_level=2,
                action_type="sequence.email.send",
                title=f"Send sequence step for {lead.email}",
                payload_json=json.dumps(
                    {
                        "enrollment_id": str(enrollment.id),
                        "lead_id": str(lead.id),
                        "template": step.template,
                        "subject": "Follow-up",
                        "body": draft_email_from_facts(db, tenant_id, step.template),
                    }
                ),
                status="pending",
                entity_type="lead",
                entity_id=str(lead.id),
                idempotency_key=key,
            )
        )
    return "email_queued"


def _advance(db: Session, enrollment: SequenceEnrollment, step: SequenceStep) -> None:
    nxt = db.scalar(
        select(SequenceStep)
        .where(
            SequenceStep.sequence_id == enrollment.sequence_id,
            SequenceStep.deleted_at.is_(None),
            SequenceStep.position > step.position,
        )
        .order_by(SequenceStep.position.asc())
    )
    if nxt is None:
        enrollment.status = "completed"
        enrollment.next_run_at = None
        return
    enrollment.current_step = nxt.position
    enrollment.next_run_at = datetime.now(UTC) + timedelta(days=max(nxt.delay_days, 0))


def link_journey(db: Session, *, tenant_id: UUID, actor_id: UUID, journey_key: str, entity_type: str, entity_id: str, role: str) -> None:
    existing = db.scalar(
        select(JourneyLink).where(
            JourneyLink.tenant_id == tenant_id,
            JourneyLink.journey_key == journey_key,
            JourneyLink.entity_type == entity_type,
            JourneyLink.entity_id == entity_id,
            JourneyLink.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return
    db.add(
        JourneyLink(
            tenant_id=tenant_id,
            created_by=actor_id,
            journey_key=journey_key,
            entity_type=entity_type,
            entity_id=entity_id,
            role=role,
        )
    )


def record_sales_qualification(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    meeting: MeetingRecord | None,
    qualified: bool,
    summary: str,
) -> Opportunity | None:
    if meeting is not None:
        db.add(
            StageEvidence(
                tenant_id=tenant_id,
                created_by=actor_id,
                entity_type="meeting",
                entity_id=str(meeting.id),
                stage="qualification",
                kind="meeting_outcome",
                summary=summary,
                source="human",
            )
        )
    if not qualified:
        upsert_state(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            entity_type="lead",
            entity_id=str(lead.id),
            state="BLOCKED",
            last_action="meeting_not_qualified",
            next_action="nurture",
            blocked_reason=summary or "Meeting did not establish sales qualification",
        )
        mark_execution(
            db,
            tenant_id=tenant_id,
            entity_id=str(lead.id),
            execution_status="completed",
            business_state="nurture",
        )
        return None
    if lead.account_id is None:
        upsert_state(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            entity_type="lead",
            entity_id=str(lead.id),
            state="BLOCKED",
            last_action="handoff_blocked",
            next_action="attach_account",
            blocked_reason="A sales-qualified lead needs an account before an opportunity is created",
        )
        return None
    existing = db.scalar(
        select(Opportunity).where(
            Opportunity.tenant_id == tenant_id,
            Opportunity.account_id == lead.account_id,
            Opportunity.name == f"Inbound: {lead.company_name or lead.email}",
            Opportunity.deleted_at.is_(None),
            Opportunity.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    if existing is not None:
        return existing
    opportunity = Opportunity(
        tenant_id=tenant_id,
        created_by=actor_id,
        account_id=lead.account_id,
        name=f"Inbound: {lead.company_name or lead.email}",
        stage="qualification",
        amount=0,
        probability=STAGE_PROBABILITY["qualification"],
        owner_id=None,
        next_step="Confirm discovery agenda",
        campaign_id=lead.campaign_id,
    )
    db.add(opportunity)
    db.flush()
    db.add(
        StageEvidence(
            tenant_id=tenant_id,
            created_by=actor_id,
            entity_type="opportunity",
            entity_id=str(opportunity.id),
            stage="qualification",
            kind="sales_qualified",
            summary=summary or "Meeting outcome recorded as sales-qualified",
            source="human",
        )
    )
    db.add(
        SlaClock(
            tenant_id=tenant_id,
            created_by=actor_id,
            entity_type="opportunity",
            entity_id=str(opportunity.id),
            transition="qualification_to_discovery",
            owner_id=opportunity.owner_id,
            due_at=datetime.now(UTC) + timedelta(days=2),
            status="running",
        )
    )
    link_journey(db, tenant_id=tenant_id, actor_id=actor_id, journey_key=f"inbound:{lead.id}", entity_type="lead", entity_id=str(lead.id), role="source")
    link_journey(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        journey_key=f"inbound:{lead.id}",
        entity_type="opportunity",
        entity_id=str(opportunity.id),
        role="handoff",
    )
    lead.status = "qualified"
    add_activity(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        activity_type="handoff",
        title="Sales-qualified opportunity created",
        body=summary,
        actor_type="human",
    )
    upsert_state(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        state="MEETING_SCHEDULED",
        last_action="handed_off",
        next_action="discover",
        blocked_reason="",
    )
    mark_execution(
        db,
        tenant_id=tenant_id,
        entity_id=str(lead.id),
        execution_status="completed",
        business_state="handed-off",
    )
    return opportunity


def stage_block_reason(db: Session, *, tenant_id: UUID, opportunity: Opportunity, target: str) -> str:
    if target in {"qualification", "closed_lost", opportunity.stage}:
        return ""
    needs = {"discovery", "solution_fit", "technical_discovery", "demo", "business_case", "proposal", "commercial_discussion", "negotiation", "procurement", "legal", "commit", "closed_won"}
    if target not in needs:
        return ""
    evidence = db.scalar(
        select(StageEvidence.id).where(
            StageEvidence.tenant_id == tenant_id,
            StageEvidence.entity_type == "opportunity",
            StageEvidence.entity_id == str(opportunity.id),
            StageEvidence.deleted_at.is_(None),
            StageEvidence.kind.in_(["sales_qualified", "meeting_outcome", "stage_note"]),
        )
    )
    if evidence is None and not (opportunity.next_step or "").strip():
        return "Stage progression needs qualification evidence or a recorded next step."
    if target in {"proposal", "commercial_discussion", "negotiation", "procurement", "legal", "commit", "closed_won"} and evidence is None:
        return "A proposal-stage move needs recorded qualification or meeting evidence."
    return ""
