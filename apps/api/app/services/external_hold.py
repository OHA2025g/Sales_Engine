"""Hold stale external work for review. Records stay in place."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import AIApproval
from app.models.assessment import ExternalEffect
from app.models.execution import ActionRequest
from app.models.identity import DomainEvent
from app.models.integrations import EmailMessage, ProviderAction
from app.models.lifecycle import SequenceEnrollment
from app.models.operating_plan import CreativeVersion
from app.services.audit import write_audit
from app.services.event_delivery import record_attempt

AUTHORIZATION_WINDOW = timedelta(days=7)
HOLD_REASON = (
    "Held for review. The work is outside the current authorization window, "
    "so it will not run when a provider is reconnected."
)
_EXTERNAL_PREFIXES = {"email", "social", "ads", "voice", "calendar", "whatsapp", "sequence"}


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def _stale(moment: datetime | None, now: datetime, window: timedelta = AUTHORIZATION_WINDOW) -> bool:
    stamped = _aware(moment)
    return stamped is not None and now - stamped > window


def external_action(action: str) -> bool:
    if action.endswith(".send") or action in {"email.acknowledge", "social.publish"}:
        return True
    return action.split(".", 1)[0] in {*_EXTERNAL_PREFIXES, "discovery"}


def _audit(db: Session, *, tenant_id: UUID, entity_type: str, entity_id: str, before: str, after: str) -> None:
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=None,
        action="external_work.hold",
        entity_type=entity_type,
        entity_id=entity_id,
        before={"status": before},
        after={"status": after, "reason": HOLD_REASON},
        actor_type="ai",
    )


def hold_stale_external_work(db: Session, *, tenant_id: UUID | None = None, now: datetime | None = None) -> dict[str, int]:
    moment = now or datetime.now(UTC)
    counts = {"events": 0, "approvals": 0, "messages": 0, "enrollments": 0, "effects": 0, "posts": 0, "actions": 0, "requests": 0}
    counts["events"] = _hold_events(db, tenant_id=tenant_id, now=moment)
    counts["approvals"] = _hold_approvals(db, tenant_id=tenant_id, now=moment)
    counts["messages"] = _hold_messages(db, tenant_id=tenant_id, now=moment)
    counts["enrollments"] = _hold_enrollments(db, tenant_id=tenant_id, now=moment)
    counts["effects"] = _hold_effects(db, tenant_id=tenant_id, now=moment)
    counts["posts"] = _hold_posts(db, tenant_id=tenant_id, now=moment)
    counts["actions"] = _hold_provider_actions(db, tenant_id=tenant_id, now=moment)
    counts["requests"] = _hold_requests(db, tenant_id=tenant_id, now=moment)
    return counts


def approval_execution_block(row: AIApproval, *, now: datetime | None = None) -> tuple[str, bool]:
    """Return a refusal and whether the approval itself should be held."""
    if row.status == "held":
        return "Held for review. It was not executed.", False
    if not external_action(row.action_type):
        return "", False
    moment = now or datetime.now(UTC)
    expires = _aware(row.expires_at)
    if expires is not None and expires < moment:
        return "Approval expired before execution.", True
    if _stale(row.created_at, moment):
        return HOLD_REASON, True
    return "", False


def _hold_events(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(DomainEvent).where(DomainEvent.delivery_status.in_(["pending", "retry", "leased"]))
    if tenant_id is not None:
        stmt = stmt.where(DomainEvent.tenant_id == tenant_id)
    held = 0
    for event in db.scalars(stmt).all():
        if not _stale(event.created_at, now):
            continue
        before = event.delivery_status
        event.delivery_status = "held"
        event.last_error = HOLD_REASON
        event.lease_until = None
        record_attempt(db, tenant_id=event.tenant_id, event=event, status="held", error=HOLD_REASON)
        _audit(db, tenant_id=event.tenant_id, entity_type="domain_event", entity_id=str(event.id), before=before, after="held")
        held += 1
    return held


def _hold_approvals(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(AIApproval).where(AIApproval.status.in_(["pending", "approved"]), AIApproval.deleted_at.is_(None))
    if tenant_id is not None:
        stmt = stmt.where(AIApproval.tenant_id == tenant_id)
    held = 0
    for row in db.scalars(stmt).all():
        reason, should_hold = approval_execution_block(row, now=now)
        if not should_hold:
            continue
        before = row.status
        row.status = "held"
        row.decision_note = ((row.decision_note + " ").strip() + " " + reason).strip()
        _audit(db, tenant_id=row.tenant_id, entity_type="ai_approval", entity_id=str(row.id), before=before, after="held")
        held += 1
    return held


def _hold_messages(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(EmailMessage).where(
        EmailMessage.deleted_at.is_(None),
        EmailMessage.status.in_(["PENDING", "RETRYING"]),
    )
    if tenant_id is not None:
        stmt = stmt.where(EmailMessage.tenant_id == tenant_id)
    held = 0
    for row in db.scalars(stmt).all():
        due = _aware(row.next_retry_at)
        expired_schedule = due is not None and now - due > AUTHORIZATION_WINDOW
        if not expired_schedule and not _stale(row.created_at, now):
            continue
        before = row.status
        row.status = "HELD"
        row.next_retry_at = None
        row.last_error = HOLD_REASON
        _audit(db, tenant_id=row.tenant_id, entity_type="email_message", entity_id=str(row.id), before=before, after="HELD")
        held += 1
    return held


def _hold_enrollments(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(SequenceEnrollment).where(
        SequenceEnrollment.deleted_at.is_(None),
        SequenceEnrollment.status == "active",
        SequenceEnrollment.next_run_at.is_not(None),
    )
    if tenant_id is not None:
        stmt = stmt.where(SequenceEnrollment.tenant_id == tenant_id)
    held = 0
    for row in db.scalars(stmt).all():
        if not _stale(row.next_run_at, now):
            continue
        before = row.status
        row.status = "held"
        row.next_run_at = None
        _audit(db, tenant_id=row.tenant_id, entity_type="sequence_enrollment", entity_id=str(row.id), before=before, after="held")
        held += 1
    return held


def _hold_effects(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(ExternalEffect).where(ExternalEffect.deleted_at.is_(None), ExternalEffect.outcome == "retry_wait")
    if tenant_id is not None:
        stmt = stmt.where(ExternalEffect.tenant_id == tenant_id)
    held = 0
    for row in db.scalars(stmt).all():
        if not _stale(row.created_at, now):
            continue
        row.outcome = "held"
        row.detail = HOLD_REASON[:500]
        _audit(db, tenant_id=row.tenant_id, entity_type="external_effect", entity_id=str(row.id), before="retry_wait", after="held")
        held += 1
    return held


def _hold_posts(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(CreativeVersion).where(CreativeVersion.deleted_at.is_(None), CreativeVersion.status == "scheduled")
    if tenant_id is not None:
        stmt = stmt.where(CreativeVersion.tenant_id == tenant_id)
    held = 0
    for row in db.scalars(stmt).all():
        if not _stale(row.scheduled_for, now):
            continue
        row.status = "held"
        _audit(db, tenant_id=row.tenant_id, entity_type="creative_version", entity_id=str(row.id), before="scheduled", after="held")
        held += 1
    return held


def _hold_provider_actions(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(ProviderAction).where(ProviderAction.deleted_at.is_(None), ProviderAction.status == "RETRYING")
    if tenant_id is not None:
        stmt = stmt.where(ProviderAction.tenant_id == tenant_id)
    held = 0
    for row in db.scalars(stmt).all():
        if not external_action(row.action_type):
            continue
        if not _stale(row.next_retry_at or row.created_at, now):
            continue
        before = row.status
        row.status = "HELD"
        row.next_retry_at = None
        row.last_error = HOLD_REASON
        _audit(db, tenant_id=row.tenant_id, entity_type="provider_action", entity_id=str(row.id), before=before, after="HELD")
        held += 1
    return held


def _hold_requests(db: Session, *, tenant_id: UUID | None, now: datetime) -> int:
    stmt = select(ActionRequest).where(
        ActionRequest.deleted_at.is_(None),
        ActionRequest.status.in_(["pending", "approved", "queued", "deferred"]),
    )
    if tenant_id is not None:
        stmt = stmt.where(ActionRequest.tenant_id == tenant_id)
    held = 0
    for row in db.scalars(stmt).all():
        if not external_action(row.action_type):
            continue
        if not _stale(row.due_at or row.created_at, now):
            continue
        before = row.status
        row.status = "held"
        row.result = HOLD_REASON
        _audit(db, tenant_id=row.tenant_id, entity_type="action_request", entity_id=str(row.id), before=before, after="held")
        held += 1
    return held
