from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.social import SocialPost
from app.providers.social import (
    LinkedInSocialPublisher,
    MetaSocialPublisher,
    NotConfiguredSocialPublisher,
    SocialPublishResult,
    get_social_publisher,
    posting_gaps,
    reaches_provider,
)
from app.services.audit import write_audit

CHANNELS = ("linkedin", "facebook", "instagram", "youtube", "x", "whatsapp")
LATER_POSTS = ("youtube", "x", "whatsapp")


def list_posts(db: Session, tenant_id: UUID) -> list[SocialPost]:
    return list(
        db.scalars(
            select(SocialPost)
            .where(SocialPost.tenant_id == tenant_id, SocialPost.deleted_at.is_(None))
            .order_by(SocialPost.created_at.desc())
        ).all()
    )


def channel_status() -> list[dict]:
    settings = get_settings()
    rows = []
    for channel, mode in (
        ("linkedin", settings.linkedin_posting_mode or "mock"),
        ("facebook", settings.meta_posting_mode or "mock"),
        ("instagram", settings.meta_posting_mode or "mock"),
    ):
        active = reaches_provider(mode)
        missing = posting_gaps(settings, channel) if active else []
        rows.append(
            {
                "channel": channel,
                "mode": mode.strip().lower(),
                "configured": not missing and active,
                "missing": missing,
            }
        )
    prepared = {
        "youtube": settings.youtube_configured,
        "x": settings.x_configured,
        "whatsapp": settings.whatsapp_configured,
    }
    for channel, configured in prepared.items():
        rows.append(
            {
                "channel": channel,
                "mode": "not_configured",
                "configured": configured,
                "missing": [] if configured else posting_gaps(settings, channel),
            }
        )
    return rows


def publish_post(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    channel: str,
    body: str,
    link_url: str = "",
    image_url: str = "",
) -> SocialPost:
    from app.services.action_requests import upsert_action_request
    from app.services.dispatcher import _channel_blocked
    from app.services.provider_resolve import resolve_provider

    normalized = channel.strip().lower()
    blocked = _channel_blocked(db, tenant_id, "social.publish")
    if blocked:
        row = SocialPost(
            tenant_id=tenant_id,
            created_by=actor_id,
            channel=normalized,
            body=body,
            link_url=link_url,
            image_url=image_url,
            status="blocked",
            provider="",
            external_id="",
            is_mock=False,
            error=blocked,
        )
        db.add(row)
        db.flush()
        upsert_action_request(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            approval=None,
            action_type="social.publish",
            status="blocked",
            result=blocked,
            channel=normalized,
            entity_type="social_post",
            entity_id=str(row.id),
            dedupe_key=f"social:{row.id}",
        )
        return row
    settings = get_settings()
    if normalized in LATER_POSTS:
        missing = posting_gaps(settings, normalized)
        if missing:
            result = NotConfiguredSocialPublisher(normalized, missing).publish(body=body, link_url=link_url, image_url=image_url)
        else:
            result = SocialPublishResult(
                ok=False,
                provider=normalized,
                is_mock=False,
                reason=f"{normalized} credentials are saved. Publishing stays off until this provider is connected.",
            )
        return _store_post(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            channel=normalized,
            body=body,
            link_url=link_url,
            image_url=image_url,
            status="not_configured",
            result=result,
        )
    provider_name = "linkedin-post" if normalized == "linkedin" else "meta-post"
    live_mode = (settings.linkedin_posting_mode if normalized == "linkedin" else settings.meta_posting_mode) or "mock"
    resolved = resolve_provider(
        db,
        tenant_id=tenant_id,
        provider=provider_name,
        live_mode=live_mode.strip().lower(),
        deployment_configured=False,
    )
    publisher = get_social_publisher(normalized)
    if resolved.mode == "LIVE" and resolved.secrets.get("access_token"):
        if normalized == "linkedin":
            publisher = LinkedInSocialPublisher(
                token=resolved.secrets.get("access_token", ""),
                organization_id=resolved.secrets.get("organization_id", ""),
            )
        elif normalized in {"facebook", "instagram"}:
            publisher = MetaSocialPublisher(
                page_id=resolved.secrets.get("page_id", ""),
                page_token=resolved.secrets.get("access_token", ""),
                instagram_id=resolved.secrets.get("instagram_id", ""),
            )
    if isinstance(publisher, MetaSocialPublisher):
        result = publisher.publish(body=body, link_url=link_url, image_url=image_url, instagram=normalized == "instagram")
    else:
        result = publisher.publish(body=body, link_url=link_url, image_url=image_url)
    status = "published" if result.ok and not result.is_mock else ("mock" if result.is_mock else "failed")
    return _store_post(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        channel=normalized,
        body=body,
        link_url=link_url,
        image_url=image_url,
        status=status,
        result=result,
    )


def _store_post(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    channel: str,
    body: str,
    link_url: str,
    image_url: str,
    status: str,
    result: SocialPublishResult,
) -> SocialPost:
    row = SocialPost(
        tenant_id=tenant_id,
        created_by=actor_id,
        channel=channel,
        body=body,
        link_url=link_url,
        image_url=image_url,
        status=status,
        provider=result.provider,
        external_id=result.external_id,
        is_mock=result.is_mock,
        error="" if result.ok else result.reason,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="social.publish",
        entity_type="social_post",
        entity_id=str(row.id),
        after={"channel": channel, "status": status, "provider": result.provider, "is_mock": result.is_mock},
    )
    return row
