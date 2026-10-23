from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pilot import SchedulerHeartbeat
from app.services.provider_metrics import CELERY_BEAT_UP, CELERY_WORKERS


def record_beat(db: Session, *, key: str = "celery_beat", leader_token: str = "") -> SchedulerHeartbeat:
    row = db.get(SchedulerHeartbeat, key)
    if row is None:
        row = SchedulerHeartbeat(id=key)
        db.add(row)
    row.last_beat_at = datetime.now(UTC)
    row.detail = "ok"
    if leader_token:
        row.leader_token = leader_token
    elif not row.leader_token:
        row.leader_token = "local"
    if key == "celery_beat":
        CELERY_BEAT_UP.set(1)
    elif key == "celery_worker":
        CELERY_WORKERS.set(1)
    db.flush()
    return row


def record_worker(count: int = 1) -> None:
    CELERY_WORKERS.set(count)


def beat_status(
    db: Session,
    *,
    key: str = "celery_beat",
    stale_after: timedelta = timedelta(minutes=20),
) -> dict:
    row = db.scalar(select(SchedulerHeartbeat).where(SchedulerHeartbeat.id == key))
    if row is None or row.last_beat_at is None:
        if key == "celery_beat":
            CELERY_BEAT_UP.set(0)
        return {"state": "unknown", "scheduler_unhealthy": True, "last_beat_at": None}
    stamped = row.last_beat_at if row.last_beat_at.tzinfo else row.last_beat_at.replace(tzinfo=UTC)
    unhealthy = datetime.now(UTC) - stamped > stale_after
    if key == "celery_beat":
        CELERY_BEAT_UP.set(0 if unhealthy else 1)
    return {
        "state": "unhealthy" if unhealthy else "ok",
        "scheduler_unhealthy": unhealthy,
        "last_beat_at": stamped,
    }
