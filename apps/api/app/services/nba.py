from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import Customer, Lead, NextBestAction, Opportunity, Renewal
from app.models.lifecycle import AdvocacyAsset
from app.models.post_sale import ExpansionRecommendation


def generate_for_opportunity(db: Session, tenant_id: UUID, opportunity: Opportunity, actor_id: UUID) -> NextBestAction:
    if not opportunity.next_step:
        action = "Set a concrete next step and meeting date"
        reason = "Opportunity has no next step recorded"
        priority = "high"
    elif opportunity.stage in {"proposal", "negotiation"}:
        action = "Confirm economic buyer and commercial approval path"
        reason = f"Late-stage deal in {opportunity.stage} needs buying committee coverage"
        priority = "high"
    else:
        action = "Advance discovery with a written summary to the champion"
        reason = f"Stage {opportunity.stage} is missing documented qualification depth"
        priority = "medium"
    row = NextBestAction(
        tenant_id=tenant_id,
        created_by=actor_id,
        entity_type="opportunity",
        entity_id=str(opportunity.id),
        action=action,
        reason=reason,
        priority=priority,
        confidence=78,
        expected_impact="Reduce stall risk",
        owner_id=opportunity.owner_id,
    )
    db.add(row)
    return row


def steps_for_lead(lead: Lead) -> list[str]:
    name = f"{lead.first_name} {lead.last_name}".strip() or "this person"
    company = lead.company_name or "the company on the record"
    title = lead.title or "the role on the record"
    source = lead.source or "the recorded source"
    if lead.opt_out:
        return [
            f"Do not email or message {name}.",
            "Leave the opt-out in place. Do not start a sequence.",
            "Write any new request in the ledger only.",
        ]
    if lead.status == "meeting_scheduled":
        return [
            f"Open the meeting already booked with {name}.",
            f"Prepare the agenda from {title} at {company} and the notes on this lead.",
            "Write down the success criteria and the decision process you need from that meeting.",
            "Keep the meeting with a person. Do not send a follow-up until the outcome is recorded.",
        ]
    if not lead.consent_email and not lead.consent_whatsapp:
        return [
            f"Do not email or message {name}. Neither email nor WhatsApp consent is on file.",
            "Keep any research in the ledger.",
            "Ask for email or WhatsApp consent before outreach.",
            "Come back and draft the first message only after that consent is recorded.",
        ]
    steps = [
        f"Confirm {name}, {title}, at {company}. Source is {source}.",
        "Read the email draft. Remove any line that is not true for this person. Do not add a meeting, a price, or a result that is not on the record.",
        "Read the WhatsApp draft. Keep it to a few lines and make it say the same thing as the email.",
    ]
    if lead.consent_email:
        steps.append("Leave the email as a draft. It is not sent until someone approves it.")
    else:
        steps.append("Do not send the email. Email consent is not on file.")
    if lead.consent_whatsapp:
        steps.append("Leave the WhatsApp message as a draft. It is not sent until someone approves it.")
    else:
        steps.append("Do not send the WhatsApp message. WhatsApp consent is not on file.")
    steps.append("When both drafts are accurate, they wait in Approvals. Nothing goes out until that approval.")
    return steps


def generate_for_lead(db: Session, tenant_id: UUID, lead: Lead, actor_id: UUID) -> NextBestAction:
    latest = db.scalar(
        select(NextBestAction)
        .where(
            NextBestAction.tenant_id == tenant_id,
            NextBestAction.entity_type == "lead",
            NextBestAction.entity_id == str(lead.id),
        )
        .limit(1)
    )
    _ = latest
    if lead.opt_out:
        action = "Do not contact — honor suppression"
        reason = "Lead is opted out"
        priority = "high"
    elif lead.status == "meeting_scheduled":
        action = "Prepare for the booked meeting"
        reason = "A meeting is on the calendar. Last strategic meeting stays human-owned."
        priority = "high"
    elif not lead.consent_email:
        action = "Use consented channel only; log research internally"
        reason = "No email consent on file"
        priority = "medium"
    else:
        action = "Draft a personalized first-touch email for approval"
        reason = "Lead is eligible for drafted outreach"
        priority = "medium"
    row = NextBestAction(
        tenant_id=tenant_id,
        created_by=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        action=action,
        reason=reason,
        priority=priority,
        confidence=74,
        expected_impact="Move lead to conversation",
    )
    db.add(row)
    return row


def _latest(db: Session, tenant_id: UUID, entity_type: str, entity_id: str) -> NextBestAction | None:
    return db.scalar(
        select(NextBestAction)
        .where(
            NextBestAction.tenant_id == tenant_id,
            NextBestAction.entity_type == entity_type,
            NextBestAction.entity_id == entity_id,
            NextBestAction.status == "open",
        )
        .order_by(NextBestAction.created_at.desc())
    )


def generate_for_customer(db: Session, tenant_id: UUID, customer: Customer, actor_id: UUID) -> NextBestAction:
    existing = _latest(db, tenant_id, "customer", str(customer.id))
    if customer.lifecycle_state == "AT_RISK":
        action, reason, priority = "Resolve onboarding or health risk", "Customer is at risk", "high"
    elif customer.lifecycle_state in {"ONBOARDING", "NEW_CUSTOMER", "IMPLEMENTING"}:
        action, reason, priority = "Complete the next onboarding milestone", "Onboarding is in progress", "high"
    elif customer.lifecycle_state in {"RENEWAL_UPCOMING", "RENEWAL_IN_PROGRESS"}:
        action, reason, priority = "Prepare renewal", "Renewal window is open", "high"
    else:
        action, reason, priority = "Schedule QBR", "Keep the executive cadence", "medium"
    if existing and existing.action == action:
        return existing
    row = NextBestAction(
        tenant_id=tenant_id,
        created_by=actor_id,
        entity_type="customer",
        entity_id=str(customer.id),
        action=action,
        reason=reason,
        priority=priority,
        confidence=76,
        expected_impact="Protect or expand post-sale revenue",
        owner_id=customer.csm_owner_id or customer.owner_id,
    )
    db.add(row)
    return row


def generate_for_renewal(db: Session, tenant_id: UUID, renewal: Renewal, actor_id: UUID) -> NextBestAction:
    existing = db.scalar(
        select(NextBestAction).where(
            NextBestAction.tenant_id == tenant_id,
            NextBestAction.entity_type == "renewal",
            NextBestAction.entity_id == str(renewal.id),
            NextBestAction.status == "open",
            NextBestAction.deleted_at.is_(None),
        )
    )
    if existing is not None:
        existing.action = renewal.recommended_action or existing.action
        existing.reason = f"Readiness {renewal.readiness}"
        return existing
    row = NextBestAction(
        tenant_id=tenant_id,
        created_by=actor_id,
        entity_type="renewal",
        entity_id=str(renewal.id),
        action=renewal.recommended_action or "Prepare renewal",
        reason=f"Readiness {renewal.readiness}",
        priority="high",
        confidence=renewal.confidence or 60,
        expected_impact="Protect recurring revenue",
        owner_id=renewal.owner_id,
    )
    db.add(row)
    return row


def generate_for_expansion(db: Session, tenant_id: UUID, rec: ExpansionRecommendation, actor_id: UUID) -> NextBestAction:
    existing = db.scalar(
        select(NextBestAction).where(
            NextBestAction.tenant_id == tenant_id,
            NextBestAction.entity_type == "customer",
            NextBestAction.entity_id == str(rec.customer_id),
            NextBestAction.action == rec.title,
            NextBestAction.status == "open",
            NextBestAction.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    row = NextBestAction(
        tenant_id=tenant_id,
        created_by=actor_id,
        entity_type="customer",
        entity_id=str(rec.customer_id),
        action=rec.title,
        reason=rec.reason,
        priority="medium",
        confidence=rec.confidence,
        expected_impact="Expand footprint without inventing pipeline value",
    )
    db.add(row)
    return row


def generate_for_advocacy(db: Session, tenant_id: UUID, asset: AdvocacyAsset, actor_id: UUID) -> NextBestAction:
    existing = db.scalar(
        select(NextBestAction).where(
            NextBestAction.tenant_id == tenant_id,
            NextBestAction.entity_type == "customer",
            NextBestAction.entity_id == str(asset.customer_id or asset.account_id),
            NextBestAction.action.startswith("Request "),
            NextBestAction.status == "open",
            NextBestAction.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    row = NextBestAction(
        tenant_id=tenant_id,
        created_by=actor_id,
        entity_type="customer",
        entity_id=str(asset.customer_id or asset.account_id),
        action=f"Request {asset.advocacy_type or asset.kind} from the customer",
        reason=f"advocacy-rules-v1 score {asset.eligibility_score or asset.readiness}",
        priority="medium",
        confidence=asset.eligibility_score or asset.readiness,
        expected_impact="Earn a reference without inventing a quote",
    )
    db.add(row)
    return row
