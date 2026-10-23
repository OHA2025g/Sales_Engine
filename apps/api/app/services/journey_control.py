"""Pause can resume. Cancel cannot. In-flight effects still reconcile."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.autonomy import AutomationIdempotencyKey, AutonomousRun


def control_journey(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    run: AutonomousRun,
    action: str,
    idempotency_key: str,
) -> dict:
    if action not in {"pause", "resume", "cancel"}:
        raise HTTPException(status_code=422, detail="Action must be pause, resume, or cancel")
    stored_key = f"journey:{action}:{run.id}:{idempotency_key}"
    existing = db.scalar(
        select(AutomationIdempotencyKey).where(
            AutomationIdempotencyKey.tenant_id == tenant_id,
            AutomationIdempotencyKey.key == stored_key,
            AutomationIdempotencyKey.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return {"journey_id": run.id, "job_id": existing.result_ref, "status": existing.window or run.status}

    if run.cancelled_at is not None or run.status == "cancelled":
        if action == "resume":
            raise HTTPException(status_code=409, detail="A cancelled journey cannot resume")
        if action == "pause":
            raise HTTPException(status_code=409, detail="A cancelled journey cannot be paused")

    now = datetime.now(UTC)
    if action == "pause":
        if run.status != "paused":
            run.status = "paused"
            run.paused_at = now
            run.business_state = "paused"
    elif action == "resume":
        if run.status != "paused":
            raise HTTPException(status_code=409, detail="Only a paused journey can resume")
        run.status = "running"
        run.paused_at = None
        run.business_state = "running"
    else:
        if run.status != "cancelled":
            run.status = "cancelled"
            run.cancelled_at = now
            run.finished_at = now
            run.business_state = "cancelled"
    job_id = str(uuid4())
    db.add(
        AutomationIdempotencyKey(
            tenant_id=tenant_id,
            created_by=actor_id,
            key=stored_key,
            workflow="journey_control",
            entity_id=str(run.id),
            action_type=action,
            window=run.status,
            result_ref=job_id,
        )
    )
    db.flush()
    return {"journey_id": run.id, "job_id": job_id, "status": run.status}
