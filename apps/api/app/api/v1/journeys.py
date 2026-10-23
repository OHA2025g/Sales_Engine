from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_permission
from app.db.session import get_db
from app.models.autonomy import AutonomousRun
from app.models.lifecycle import MeetingRecord
from app.schemas.assessment import DiscoveryBookingIn, JourneyContinueOut, JourneyControlOut, NextActionOut
from app.schemas.common import Envelope
from app.services.acknowledgement import continue_corrected_journey
from app.services.audit import write_audit
from app.services.autopilot_settings import get_or_create_settings
from app.services.calendar_booking import cancel_booked_meeting, reschedule_booked_meeting
from app.services.journey_control import control_journey
from app.services.operations import journey_next_action
from app.services.query import get_owned

router = APIRouter(prefix="/journeys", tags=["journeys"])


def _control(
    run_id: UUID,
    action: str,
    db: Session,
    ctx: AuthContext,
    idempotency_key: str,
) -> Envelope[JourneyControlOut]:
    run = get_owned(db, AutonomousRun, ctx.tenant_id, run_id)
    result = control_journey(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        run=run,
        action=action,
        idempotency_key=idempotency_key,
    )
    write_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        action=f"journey.{action}",
        entity_type="autonomous_run",
        entity_id=str(run.id),
        after=result,
        correlation_id=ctx.correlation_id,
    )
    db.commit()
    return Envelope(data=JourneyControlOut.model_validate(result))


@router.post("/{run_id}/pause", response_model=Envelope[JourneyControlOut])
def pause_journey(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("autonomy.write"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Envelope[JourneyControlOut]:
    return _control(run_id, "pause", db, ctx, idempotency_key)


@router.post("/{run_id}/resume", response_model=Envelope[JourneyControlOut])
def resume_journey(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("autonomy.write"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Envelope[JourneyControlOut]:
    return _control(run_id, "resume", db, ctx, idempotency_key)


@router.post("/{run_id}/cancel", response_model=Envelope[JourneyControlOut])
def cancel_journey(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("autonomy.write"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Envelope[JourneyControlOut]:
    return _control(run_id, "cancel", db, ctx, idempotency_key)


@router.get("/{run_id}/next-action", response_model=Envelope[NextActionOut])
def next_action(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("command_center.read"))],
) -> Envelope[NextActionOut]:
    run = get_owned(db, AutonomousRun, ctx.tenant_id, run_id)
    return Envelope(data=NextActionOut.model_validate(journey_next_action(db, tenant_id=ctx.tenant_id, run=run)))


@router.post("/{run_id}/continue", response_model=Envelope[JourneyContinueOut])
def continue_journey(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("autonomy.write"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Envelope[JourneyContinueOut]:
    run = get_owned(db, AutonomousRun, ctx.tenant_id, run_id)
    settings = get_or_create_settings(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id)
    result = continue_corrected_journey(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        run=run,
        settings=settings,
        idempotency_key=idempotency_key,
    )
    write_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        action="journey.continue",
        entity_type="autonomous_run",
        entity_id=str(run.id),
        after=result,
        correlation_id=ctx.correlation_id,
    )
    db.commit()
    return Envelope(data=JourneyContinueOut.model_validate(result))


@router.post("/meetings/{meeting_id}/reschedule", response_model=Envelope[dict])
def reschedule(
    meeting_id: UUID,
    body: DiscoveryBookingIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("meetings.write"))],
) -> Envelope[dict]:
    meeting = get_owned(db, MeetingRecord, ctx.tenant_id, meeting_id)
    detail = reschedule_booked_meeting(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        meeting_id=meeting.id,
        start_at=body.start_at,
        end_at=body.end_at,
        timezone=body.timezone,
    )
    db.commit()
    return Envelope(data={"meeting_id": str(meeting.id), "detail": detail, "status": meeting.status})


@router.post("/meetings/{meeting_id}/cancel", response_model=Envelope[dict])
def cancel(
    meeting_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("meetings.write"))],
) -> Envelope[dict]:
    meeting = get_owned(db, MeetingRecord, ctx.tenant_id, meeting_id)
    detail = cancel_booked_meeting(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, meeting_id=meeting.id)
    db.commit()
    db.refresh(meeting)
    return Envelope(data={"meeting_id": str(meeting.id), "detail": detail, "status": meeting.status})
