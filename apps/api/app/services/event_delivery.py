"""Claim, retry, and replay domain events without acknowledging failures."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.execution import EventDeliveryAttempt
from app.models.identity import DomainEvent

MAX_ATTEMPTS = 5
LEASE = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


def record_attempt(
    db: Session,
    *,
    tenant_id: UUID,
    event: DomainEvent,
    status: str,
    error: str = "",
    actor_id: UUID | None = None,
) -> None:
    db.add(
        EventDeliveryAttempt(
            tenant_id=tenant_id,
            created_by=actor_id,
            event_id=event.id,
            consumer=event.consumer or "orchestrator",
            attempt=event.attempts or 1,
            status=status,
            error=error[:1000],
            finished_at=_now(),
        )
    )


def claim_next_event(
    db: Session,
    *,
    tenant_id: UUID | None,
    limit_one: bool = True,
) -> DomainEvent | None:
    now = _now()
    stmt = (
        select(DomainEvent)
        .where(
            DomainEvent.processed_at.is_(None),
            DomainEvent.delivery_status.in_(["pending", "retry", "leased"]),
            or_(DomainEvent.next_attempt_at.is_(None), DomainEvent.next_attempt_at <= now),
            or_(DomainEvent.lease_until.is_(None), DomainEvent.lease_until < now),
        )
        .order_by(DomainEvent.created_at.asc())
        .limit(1 if limit_one else 1)
    )
    if tenant_id is not None:
        stmt = stmt.where(DomainEvent.tenant_id == tenant_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    event = db.execute(stmt).scalars().first()
    if event is None:
        return None
    event.delivery_status = "leased"
    event.attempts = int(event.attempts or 0) + 1
    event.lease_until = now + LEASE
    event.lease_token = uuid4().hex
    event.consumer = event.consumer or "orchestrator"
    db.flush()
    return event


def acknowledge(db: Session, event: DomainEvent, *, actor_id: UUID | None = None) -> None:
    event.delivery_status = "succeeded"
    event.processed_at = _now()
    event.lease_until = None
    event.last_error = ""
    record_attempt(db, tenant_id=event.tenant_id, event=event, status="succeeded", actor_id=actor_id)


def fail_delivery(db: Session, event: DomainEvent, error: str, *, actor_id: UUID | None = None) -> str:
    event.last_error = error[:1000]
    event.lease_until = None
    event.lease_token = ""
    if int(event.attempts or 0) >= MAX_ATTEMPTS:
        event.delivery_status = "dead"
        event.processed_at = None
        record_attempt(db, tenant_id=event.tenant_id, event=event, status="dead", error=error, actor_id=actor_id)
        return "dead"
    delay = min(60 * (2 ** max(int(event.attempts or 1) - 1, 0)), 3600)
    event.delivery_status = "retry"
    event.processed_at = None
    event.next_attempt_at = _now() + timedelta(seconds=delay)
    record_attempt(db, tenant_id=event.tenant_id, event=event, status="retry", error=error, actor_id=actor_id)
    return "retry"


def reject_delivery(db: Session, event: DomainEvent, reason: str, *, actor_id: UUID | None = None) -> None:
    event.delivery_status = "rejected"
    event.processed_at = _now()
    event.last_error = reason[:1000]
    event.lease_until = None
    record_attempt(db, tenant_id=event.tenant_id, event=event, status="rejected", error=reason, actor_id=actor_id)


def replay_event(db: Session, event: DomainEvent, *, actor_id: UUID | None = None) -> str:
    if event.delivery_status not in {"dead", "retry", "rejected"}:
        return "Event is not waiting for replay."
    event.processed_at = None
    event.delivery_status = "pending"
    event.lease_until = None
    event.lease_token = ""
    event.next_attempt_at = None
    event.attempts = 0
    record_attempt(
        db,
        tenant_id=event.tenant_id,
        event=event,
        status="replay",
        error=event.last_error,
        actor_id=actor_id,
    )
    return "Replay queued. Earlier attempts stay in the delivery history."
