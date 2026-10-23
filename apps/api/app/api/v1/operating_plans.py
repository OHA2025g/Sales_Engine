from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_permission
from app.db.session import get_db
from app.schemas.common import Envelope
from app.services.marketing import (
    attributed_outcomes,
    authorize_version,
    generate_draft,
    preview_schedule,
    publication_evidence,
    publish_scheduled,
    record_metrics,
    research_prospects,
    resume_plan,
    review_versions,
    revise_version,
    schedule_version,
    start_operating_plan,
)
from app.services.operations import channel_readiness

router = APIRouter(prefix="/operating-plans", tags=["operating-plans"])


class VersionIn(BaseModel):
    version_id: UUID
    body: str = ""


class MetricsIn(BaseModel):
    version_id: UUID
    impressions: int | None = None
    clicks: int | None = None
    spend: str | None = None


@router.get("/readiness")
def readiness(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("autonomy.read"))],
    channel: str = "email",
) -> Envelope[dict]:
    return Envelope(data=channel_readiness(db, tenant_id=ctx.tenant_id, channel=channel))


@router.post("/start")
def start_plan(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
    channel: str = "linkedin",
    product_id: UUID | None = None,
) -> Envelope[dict]:
    data = start_operating_plan(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        channel=channel,
        product_id=product_id,
    )
    db.commit()
    return Envelope(data=data)


@router.post("/research")
def research(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    data = research_prospects(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id)
    db.commit()
    return Envelope(data=data)


@router.post("/drafts")
def drafts(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    data = generate_draft(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id)
    db.commit()
    return Envelope(data=data)


@router.get("/review")
def review(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[dict]:
    return Envelope(data=review_versions(db, ctx.tenant_id))


@router.post("/authorize")
def authorize(
    body: VersionIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    data = authorize_version(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, version_id=body.version_id)
    db.commit()
    return Envelope(data=data)


@router.post("/revise")
def revise(
    body: VersionIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    data = revise_version(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, version_id=body.version_id, body=body.body)
    db.commit()
    return Envelope(data=data)


@router.get("/schedule")
def schedule_preview(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[dict]:
    return Envelope(data=preview_schedule(db, ctx.tenant_id))


@router.post("/schedule")
def schedule(
    body: VersionIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    data = schedule_version(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, version_id=body.version_id)
    db.commit()
    return Envelope(data=data)


@router.post("/publish")
def publish(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    data = publish_scheduled(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id)
    db.commit()
    return Envelope(data=data)


@router.get("/evidence")
def evidence(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[dict]:
    return Envelope(data=publication_evidence(db, ctx.tenant_id))


@router.get("/outcomes")
def outcomes(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[dict]:
    return Envelope(data=attributed_outcomes(db, ctx.tenant_id))


@router.post("/metrics")
def metrics(
    body: MetricsIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    supplied = {key: getattr(body, key) for key in body.model_fields_set if key != "version_id" and getattr(body, key) is not None}
    data = record_metrics(db, tenant_id=ctx.tenant_id, version_id=body.version_id, metrics=supplied or None)
    db.commit()
    return Envelope(data=data)


@router.post("/resume")
def resume(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[dict]:
    data = resume_plan(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id)
    db.commit()
    return Envelope(data=data)
