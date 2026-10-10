import json
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.funnel import PublicFormKey
from app.models.social import SocialPost
from app.providers.social import (
    LinkedInSocialPublisher,
    MetaSocialPublisher,
    NotConfiguredSocialPublisher,
    SocialPublishResult,
    get_social_publisher,
    posting_gaps,
    reaches_provider,
    resolved_permalink,
)
from app.services.audit import write_audit
from app.services.public_forms import social_form_link
from app.services.query import get_owned

CHANNELS = ("linkedin", "facebook", "instagram", "youtube", "x", "whatsapp")
LATER_POSTS = ("youtube", "x", "whatsapp")
_POST_TEXT_LIMIT = 3000
_EXTRA_LINK_LIMIT = 8


def normalize_extra_links(items: list[tuple[str, str]]) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    seen: set[str] = set()
    for label, url in items:
        clean_label = " ".join(label.split())
        clean_url = url.strip()
        if not clean_label and not clean_url:
            continue
        if len(clean_label) > 80:
            raise HTTPException(status_code=422, detail="A link name must be 80 characters or fewer.")
        parsed = urlsplit(clean_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise HTTPException(status_code=422, detail="Each extra link must start with http:// or https://.")
        if len(clean_url) > 500:
            raise HTTPException(status_code=422, detail="A link must be 500 characters or fewer.")
        if clean_url in seen:
            continue
        seen.add(clean_url)
        kept.append({"label": clean_label, "url": clean_url})
    if len(kept) > _EXTRA_LINK_LIMIT:
        raise HTTPException(status_code=422, detail="A post can include up to 8 extra links.")
    return kept


def encode_extra_links(links: list[dict[str, str]]) -> str:
    if not links:
        return ""
    return json.dumps(links, separators=(",", ":"))


def compose_post_text(body: str, links: list[dict[str, str]], card_url: str = "") -> str:
    text = body.strip()
    card = card_url.strip()
    lines: list[str] = []
    for item in links:
        url = item["url"]
        if card and url == card:
            continue
        label = item["label"].strip()
        line = f"{label}: {url}" if label else url
        if line in text:
            continue
        lines.append(line)
    if not lines:
        return text
    block = "\n".join(lines)
    combined = f"{text}\n\n{block}" if text else block
    if len(combined) > _POST_TEXT_LIMIT:
        raise HTTPException(
            status_code=422,
            detail="The post text plus the extra links is longer than 3000 characters.",
        )
    return combined


def list_posts(db: Session, tenant_id: UUID) -> list[SocialPost]:
    rows = list(
        db.scalars(
            select(SocialPost)
            .where(SocialPost.tenant_id == tenant_id, SocialPost.deleted_at.is_(None))
            .order_by(SocialPost.created_at.desc())
        ).all()
    )
    _attach_permalinks(rows)
    return rows


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
    form_key_id: UUID | None = None,
    extra_links: list[tuple[str, str]] | None = None,
) -> SocialPost:
    from app.services.action_requests import upsert_action_request
    from app.services.dispatcher import _channel_blocked

    normalized = channel.strip().lower()
    link_url, attached_form_id = _linked_form(db, tenant_id, normalized, form_key_id, link_url)
    links = normalize_extra_links(extra_links or [])
    encoded_links = encode_extra_links(links)
    published_body = compose_post_text(body, links, link_url)
    blocked = _channel_blocked(db, tenant_id, "social.publish")
    if blocked:
        row = SocialPost(
            tenant_id=tenant_id,
            created_by=actor_id,
            channel=normalized,
            body=body,
            link_url=link_url,
            image_url=image_url,
            extra_links=encoded_links,
            form_key_id=attached_form_id,
            status="blocked",
            provider="",
            external_id="",
            permalink="",
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
    status, result = _send(db, tenant_id, normalized, published_body, link_url, image_url)
    return _store_post(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        channel=normalized,
        body=body,
        link_url=link_url,
        image_url=image_url,
        extra_links=encoded_links,
        form_key_id=attached_form_id,
        status=status,
        result=result,
    )


def revise_post(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    post_id: UUID,
    body: str,
    link_url: str = "",
    image_url: str = "",
    form_key_id: UUID | None = None,
    extra_links: list[tuple[str, str]] | None = None,
) -> SocialPost:
    from app.services.dispatcher import _channel_blocked

    row = get_owned(db, SocialPost, tenant_id, post_id)
    before = {
        "body": row.body,
        "link_url": row.link_url,
        "image_url": row.image_url,
        "extra_links": row.extra_links,
        "form_key_id": str(row.form_key_id) if row.form_key_id else "",
        "status": row.status,
    }
    links = normalize_extra_links(extra_links or [])
    encoded_links = encode_extra_links(links)
    if row.status == "published" and not row.is_mock:
        if row.channel == "instagram":
            raise HTTPException(
                status_code=422,
                detail="A published Instagram post cannot be changed. Publish a new post with the corrected text.",
            )
        if row.channel not in {"facebook", "linkedin"}:
            raise HTTPException(status_code=422, detail="This published post cannot be changed from here.")
        published_body = compose_post_text(body, links, row.link_url)
        result = _update_live(db, tenant_id, row, published_body)
        if not result.ok:
            raise HTTPException(status_code=422, detail=result.reason or "The live post was not changed.")
        row.body = body
        row.extra_links = encoded_links
        row.error = ""
        _audit_revision(db, tenant_id=tenant_id, actor_id=actor_id, row=row, before=before)
        return row
    link_url, attached_form_id = _linked_form(db, tenant_id, row.channel, form_key_id, link_url)
    published_body = compose_post_text(body, links, link_url)
    row.body = body
    row.link_url = link_url
    row.image_url = image_url
    row.extra_links = encoded_links
    row.form_key_id = attached_form_id
    if row.status == "mock" or row.is_mock:
        _audit_revision(db, tenant_id=tenant_id, actor_id=actor_id, row=row, before=before)
        return row
    blocked = _channel_blocked(db, tenant_id, "social.publish")
    if blocked:
        row.status = "blocked"
        row.error = blocked
        row.is_mock = False
        _audit_revision(db, tenant_id=tenant_id, actor_id=actor_id, row=row, before=before)
        return row
    status, result = _send(db, tenant_id, row.channel, published_body, link_url, image_url)
    row.status = status
    row.provider = result.provider
    row.external_id = result.external_id or row.external_id
    row.permalink = result.permalink or resolved_permalink(row.channel, row.external_id, row.permalink)
    row.is_mock = result.is_mock
    row.error = "" if result.ok else result.reason
    _audit_revision(db, tenant_id=tenant_id, actor_id=actor_id, row=row, before=before)
    return row


def _linked_form(
    db: Session,
    tenant_id: UUID,
    channel: str,
    form_key_id: UUID | None,
    link_url: str,
) -> tuple[str, UUID | None]:
    if form_key_id is None:
        return link_url, None
    key = get_owned(db, PublicFormKey, tenant_id, form_key_id)
    if key.status != "active":
        raise HTTPException(status_code=422, detail="That form is not active.")
    return social_form_link(key, channel), key.id


def _send(
    db: Session,
    tenant_id: UUID,
    normalized: str,
    body: str,
    link_url: str,
    image_url: str,
) -> tuple[str, SocialPublishResult]:
    from app.services.provider_resolve import resolve_provider

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
        return "not_configured", result
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
    return status, result


def _update_live(db: Session, tenant_id: UUID, row: SocialPost, body: str) -> SocialPublishResult:
    from app.services.provider_resolve import resolve_provider

    settings = get_settings()
    provider_name = "linkedin-post" if row.channel == "linkedin" else "meta-post"
    live_mode = (settings.linkedin_posting_mode if row.channel == "linkedin" else settings.meta_posting_mode) or "mock"
    resolved = resolve_provider(
        db,
        tenant_id=tenant_id,
        provider=provider_name,
        live_mode=live_mode.strip().lower(),
        deployment_configured=False,
    )
    publisher = get_social_publisher(row.channel)
    if resolved.mode == "LIVE" and resolved.secrets.get("access_token"):
        if row.channel == "linkedin":
            publisher = LinkedInSocialPublisher(
                token=resolved.secrets.get("access_token", ""),
                organization_id=resolved.secrets.get("organization_id", ""),
            )
        elif row.channel == "facebook":
            publisher = MetaSocialPublisher(
                page_id=resolved.secrets.get("page_id", ""),
                page_token=resolved.secrets.get("access_token", ""),
                instagram_id=resolved.secrets.get("instagram_id", ""),
            )
    if isinstance(publisher, LinkedInSocialPublisher):
        return publisher.update_commentary(external_id=row.external_id, body=body)
    if isinstance(publisher, MetaSocialPublisher) and row.channel == "facebook":
        return publisher.update_message(external_id=row.external_id, body=body)
    return SocialPublishResult(
        ok=False,
        provider=row.channel,
        is_mock=False,
        reason="This post is not connected to a live account, so the caption was not changed.",
    )


def _audit_revision(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    row: SocialPost,
    before: dict,
) -> None:
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="social.update",
        entity_type="social_post",
        entity_id=str(row.id),
        before=before,
        after={
            "body": row.body,
            "link_url": row.link_url,
            "image_url": row.image_url,
            "extra_links": row.extra_links,
            "form_key_id": str(row.form_key_id) if row.form_key_id else "",
            "status": row.status,
        },
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
    extra_links: str,
    form_key_id: UUID | None,
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
        extra_links=extra_links,
        form_key_id=form_key_id,
        status=status,
        provider=result.provider,
        external_id=result.external_id,
        permalink=result.permalink or resolved_permalink(channel, result.external_id),
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
        after={
            "channel": channel,
            "status": status,
            "provider": result.provider,
            "is_mock": result.is_mock,
            "form_key_id": str(form_key_id) if form_key_id else "",
        },
    )
    return row


def _attach_permalinks(rows: list[SocialPost]) -> None:
    token = get_settings().meta_page_access_token
    for row in rows:
        if row.status != "published":
            continue
        row.permalink = resolved_permalink(row.channel, row.external_id, row.permalink, token=token)
