from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_permission
from app.db.session import get_db
from app.models.funnel import PublicFormKey
from app.models.social import SocialPost
from app.schemas.common import Envelope, Meta
from app.schemas.social import (
    SocialChannelStatus,
    SocialDraftIn,
    SocialDraftOut,
    SocialPostIn,
    SocialPostOut,
    SocialPostUpdate,
)
from app.services.content import draft_social_copy
from app.services.social import CHANNELS, channel_status, list_posts, publish_post, revise_post
from app.services.social_media import store_social_image

router = APIRouter(prefix="/social", tags=["social"])


def _posts_out(db: Session, tenant_id: UUID, rows: list[SocialPost]) -> list[SocialPostOut]:
    ids = [row.form_key_id for row in rows if row.form_key_id]
    names: dict[UUID, str] = {}
    if ids:
        keys = db.scalars(select(PublicFormKey).where(PublicFormKey.tenant_id == tenant_id, PublicFormKey.id.in_(ids))).all()
        names = {key.id: key.name for key in keys}
    data: list[SocialPostOut] = []
    for row in rows:
        item = SocialPostOut.model_validate(row)
        item.form_name = names.get(row.form_key_id, "") if row.form_key_id else ""
        data.append(item)
    return data


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
    rows = list_posts(db, ctx.tenant_id)
    db.commit()
    data = _posts_out(db, ctx.tenant_id, rows)
    return Envelope(data=data, meta=Meta(total=len(data)))


@router.post("/draft", response_model=Envelope[SocialDraftOut])
def draft_social_post(
    body: SocialDraftIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialDraftOut]:
    drafted = draft_social_copy(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, channel=body.channel)
    db.commit()
    return Envelope(data=SocialDraftOut.model_validate(drafted))


@router.post("/images", response_model=Envelope[dict])
async def upload_social_image(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
    file: Annotated[UploadFile, File()],
) -> Envelope[dict]:
    data = await file.read()
    url = store_social_image(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, data=data)
    db.commit()
    return Envelope(data={"url": url})


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
        form_key_id=body.form_key_id,
        extra_links=[(item.label, item.url) for item in body.extra_links],
    )
    db.commit()
    db.refresh(row)
    return Envelope(data=_posts_out(db, ctx.tenant_id, [row])[0])


@router.patch("/posts/{post_id}", response_model=Envelope[SocialPostOut])
def update_social_post(
    post_id: UUID,
    body: SocialPostUpdate,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialPostOut]:
    row = revise_post(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        post_id=post_id,
        body=body.body.strip(),
        link_url=body.link_url.strip(),
        image_url=body.image_url.strip(),
        form_key_id=body.form_key_id,
        extra_links=[(item.label, item.url) for item in body.extra_links],
    )
    db.commit()
    db.refresh(row)
    return Envelope(data=_posts_out(db, ctx.tenant_id, [row])[0])
