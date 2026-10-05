from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_permission
from app.db.session import get_db
from app.schemas.common import Envelope, Meta
from app.schemas.social import SocialChannelStatus, SocialPostIn, SocialPostOut
from app.services.social import CHANNELS, channel_status, list_posts, publish_post

router = APIRouter(prefix="/social", tags=["social"])


@router.get("/status", response_model=Envelope[list[SocialChannelStatus]])
def social_status(
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[list[SocialChannelStatus]]:
    _ = ctx
    rows = [SocialChannelStatus.model_validate(row) for row in channel_status()]
    return Envelope(data=rows, meta=Meta(total=len(rows)))


@router.get("/posts", response_model=Envelope[list[SocialPostOut]])
def social_posts(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[list[SocialPostOut]]:
    rows = [SocialPostOut.model_validate(row) for row in list_posts(db, ctx.tenant_id)]
    return Envelope(data=rows, meta=Meta(total=len(rows)))


@router.post("/posts", response_model=Envelope[SocialPostOut])
def create_social_post(
    body: SocialPostIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialPostOut]:
    channel = body.channel.strip().lower()
    if channel not in CHANNELS:
        raise HTTPException(status_code=422, detail="Channel must be linkedin, facebook, instagram, youtube, x, or whatsapp.")
    row = publish_post(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        channel=channel,
        body=body.body.strip(),
        link_url=body.link_url.strip(),
        image_url=body.image_url.strip(),
    )
    db.commit()
    db.refresh(row)
    return Envelope(data=SocialPostOut.model_validate(row))
