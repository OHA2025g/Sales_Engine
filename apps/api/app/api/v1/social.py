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
    SocialBriefIn,
    SocialChannelStatus,
    SocialComposeOut,
    SocialCreativeIn,
    SocialCreativeOut,
    SocialDraftIn,
    SocialDraftOut,
    SocialPostIn,
    SocialPostOut,
    SocialPostUpdate,
    SocialSubmissionIn,
    SocialSubmissionOut,
)
from app.services.content import draft_social_copy
from app.services.social import (
    CHANNELS,
    briefs_for_posts,
    channel_status,
    list_posts,
    publish_post,
    revise_post,
    submit_for_approval,
    submit_revision,
)
from app.services.social_creative import compose_post, create_banner, create_short_video
from app.services.social_media import store_social_image

router = APIRouter(prefix="/social", tags=["social"])


def _posts_out(db: Session, tenant_id: UUID, rows: list[SocialPost]) -> list[SocialPostOut]:
    ids = [row.form_key_id for row in rows if row.form_key_id]
    names: dict[UUID, str] = {}
    if ids:
        keys = db.scalars(select(PublicFormKey).where(PublicFormKey.tenant_id == tenant_id, PublicFormKey.id.in_(ids))).all()
        names = {key.id: key.name for key in keys}
    briefs = briefs_for_posts(db, tenant_id, {str(row.id) for row in rows})
    data: list[SocialPostOut] = []
    for row in rows:
        item = SocialPostOut.model_validate(row)
        item.form_name = names.get(row.form_key_id, "") if row.form_key_id else ""
        brief = briefs.get(str(row.id))
        if brief:
            item.headline = brief["headline"]
            item.keyword = brief["keyword"]
            item.ranking_parameter = brief["ranking_parameter"]
            item.snippet = brief["snippet"]
            item.context = brief["context"]
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


@router.post("/compose", response_model=Envelope[SocialComposeOut])
def compose_social_post(
    body: SocialBriefIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialComposeOut]:
    written = compose_post(
        db,
        tenant_id=ctx.tenant_id,
        headline=body.headline,
        keyword=body.keyword,
        ranking_parameter=body.ranking_parameter,
        snippet=body.snippet,
        context=body.context,
    )
    db.commit()
    return Envelope(data=SocialComposeOut(body=written))


@router.post("/banner", response_model=Envelope[SocialCreativeOut])
def banner_social_post(
    body: SocialCreativeIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialCreativeOut]:
    url, note = create_banner(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        headline=body.headline,
        keyword=body.keyword,
        ranking_parameter=body.ranking_parameter,
        snippet=body.snippet,
        context=body.context,
        body=body.body,
    )
    db.commit()
    return Envelope(data=SocialCreativeOut(url=url, note=note, kind="image"))


@router.post("/video", response_model=Envelope[SocialCreativeOut])
def video_social_post(
    body: SocialCreativeIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialCreativeOut]:
    url, note = create_short_video(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        headline=body.headline,
        keyword=body.keyword,
        ranking_parameter=body.ranking_parameter,
        snippet=body.snippet,
        context=body.context,
        body=body.body,
    )
    db.commit()
    return Envelope(data=SocialCreativeOut(url=url, note=note, kind="video" if not note else "image"))


@router.post("/submissions", response_model=Envelope[SocialSubmissionOut])
def submit_social_post(
    body: SocialSubmissionIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialSubmissionOut]:
    approval, rows = submit_for_approval(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        headline=body.headline,
        body=body.body,
        keyword=body.keyword,
        ranking_parameter=body.ranking_parameter,
        snippet=body.snippet,
        context=body.context,
        image_url=body.image_url,
        video_url=body.video_url,
        form_key_id=body.form_key_id,
        channels=body.channels,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return Envelope(
        data=SocialSubmissionOut(approval_id=approval.id, posts=_posts_out(db, ctx.tenant_id, rows))
    )


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


@router.post("/posts/{post_id}/revision", response_model=Envelope[SocialSubmissionOut])
def revise_social_submission(
    post_id: UUID,
    body: SocialSubmissionIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SocialSubmissionOut]:
    approval, rows = submit_revision(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        post_id=post_id,
        headline=body.headline,
        body=body.body,
        keyword=body.keyword,
        ranking_parameter=body.ranking_parameter,
        snippet=body.snippet,
        context=body.context,
        image_url=body.image_url,
        video_url=body.video_url,
        form_key_id=body.form_key_id,
        channels=body.channels,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return Envelope(data=SocialSubmissionOut(approval_id=approval.id, posts=_posts_out(db, ctx.tenant_id, rows)))


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
