from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.social import SocialPost
from app.providers.social import MetaSocialPublisher, get_social_publisher, posting_gaps, reaches_provider
from app.services.audit import write_audit

CHANNELS = ("linkedin", "facebook", "instagram")


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
    normalized = channel.strip().lower()
    publisher = get_social_publisher(normalized)
    if isinstance(publisher, MetaSocialPublisher):
        result = publisher.publish(body=body, link_url=link_url, image_url=image_url, instagram=normalized == "instagram")
    else:
        result = publisher.publish(body=body, link_url=link_url, image_url=image_url)
    status = "published" if result.ok and not result.is_mock else ("mock" if result.is_mock else "failed")
    row = SocialPost(
        tenant_id=tenant_id,
        created_by=actor_id,
        channel=normalized,
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
        after={"channel": normalized, "status": status, "provider": result.provider, "is_mock": result.is_mock},
    )
    return row
