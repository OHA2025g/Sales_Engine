import json
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai import AIApproval
from app.models.funnel import PublicFormKey
from app.models.social import SocialPost
from app.providers.social import (
    LinkedInSocialPublisher,
    MetaSocialPublisher,
    NotConfiguredSocialPublisher,
    SocialPublishResult,
    get_social_publisher,
    instagram_can_fetch,
    posting_gaps,
    reaches_provider,
    resolved_permalink,
)
from app.services.social_artwork import draw_banner_png
from app.services.social_media import read_social_image
from app.services.audit import write_audit
from app.services.public_forms import social_form_link
from app.services.query import get_owned

CHANNELS = ("linkedin", "facebook", "instagram", "youtube", "x", "whatsapp")
APPROVAL_CHANNELS = ("linkedin", "facebook", "instagram", "youtube")
_CHANNEL_LABELS = {"linkedin": "LinkedIn", "facebook": "Facebook", "instagram": "Instagram", "youtube": "YouTube"}
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


def live_copy(headline: str, body: str) -> str:
    text = f"{headline.strip()}\n\n{body.strip()}".strip()
    return text[:_POST_TEXT_LIMIT]


def submit_for_approval(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    headline: str,
    body: str,
    keyword: str,
    ranking_parameter: str,
    snippet: str,
    context: str,
    image_url: str = "",
    video_url: str = "",
    form_key_id: UUID | None = None,
    channels: list[str],
) -> tuple[AIApproval, list[SocialPost]]:
    chosen: list[str] = []
    for channel in channels:
        normalized = channel.strip().lower()
        if normalized not in APPROVAL_CHANNELS:
            raise HTTPException(status_code=422, detail="Choose LinkedIn, Facebook, Instagram, or YouTube.")
        if normalized not in chosen:
            chosen.append(normalized)
    if not chosen:
        raise HTTPException(status_code=422, detail="Choose at least one channel.")
    copy = live_copy(headline, body)
    rows: list[SocialPost] = []
    for normalized in chosen:
        link_url, attached_form_id = _linked_form(db, tenant_id, normalized, form_key_id, "")
        row = SocialPost(
            tenant_id=tenant_id,
            created_by=actor_id,
            channel=normalized,
            body=copy,
            link_url=link_url,
            image_url=image_url.strip(),
            video_url=video_url.strip(),
            extra_links="",
            form_key_id=attached_form_id,
            status="pending_approval",
            provider="",
            external_id="",
            permalink="",
            is_mock=False,
            error="",
        )
        db.add(row)
        rows.append(row)
    db.flush()
    names = ", ".join(_CHANNEL_LABELS[item] for item in chosen)
    approval = AIApproval(
        tenant_id=tenant_id,
        created_by=actor_id,
        action_level=2,
        action_type="social.publish",
        title=headline.strip()[:200],
        payload_json=json.dumps(
            {
                "post_ids": [str(row.id) for row in rows],
                "channels": chosen,
                "who": names,
                "why": context.strip(),
                "evidence": snippet.strip(),
                "keyword": keyword.strip(),
                "ranking_parameter": ranking_parameter.strip(),
                "risk": "Approving publishes this post on the selected channels.",
                "expected_outcome": "The post stays unpublished until this approval is accepted.",
                "message": copy,
                "image_url": image_url.strip(),
                "video_url": video_url.strip(),
            }
        ),
        status="pending",
        entity_type="social_post",
        entity_id=str(rows[0].id),
        idempotency_key=f"social.publish:{rows[0].id}",
    )
    db.add(approval)
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="social.approval_requested",
        entity_type="ai_approval",
        entity_id=str(approval.id),
        after={"channels": chosen, "posts": [str(row.id) for row in rows]},
    )
    return approval, rows


def submit_revision(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    post_id: UUID,
    headline: str,
    body: str,
    keyword: str,
    ranking_parameter: str,
    snippet: str,
    context: str,
    image_url: str = "",
    video_url: str = "",
    form_key_id: UUID | None = None,
    channels: list[str],
) -> tuple[AIApproval, list[SocialPost]]:
    current = get_owned(db, SocialPost, tenant_id, post_id)
    approval, rows = submit_for_approval(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        headline=headline,
        body=body,
        keyword=keyword,
        ranking_parameter=ranking_parameter,
        snippet=snippet,
        context=context,
        image_url=image_url,
        video_url=video_url,
        form_key_id=form_key_id,
        channels=channels,
    )
    if current.status != "published":
        current.status = "rejected"
        current.error = "Replaced by a newer edit."
        _close_replaced_approval(db, tenant_id, current.id)
    return approval, rows


def _close_replaced_approval(db: Session, tenant_id: UUID, post_id: UUID) -> None:
    pending = db.scalars(
        select(AIApproval).where(
            AIApproval.tenant_id == tenant_id,
            AIApproval.action_type == "social.publish",
            AIApproval.status == "pending",
        )
    ).all()
    for approval in pending:
        try:
            payload = json.loads(approval.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        raw_ids = [str(item) for item in payload.get("post_ids") or []]
        if str(post_id) not in raw_ids:
            continue
        still_waiting = False
        for raw_id in raw_ids:
            try:
                sibling_id = UUID(raw_id)
            except ValueError:
                continue
            sibling = db.get(SocialPost, sibling_id)
            if sibling is not None and sibling.tenant_id == tenant_id and sibling.status == "pending_approval":
                still_waiting = True
                break
        if not still_waiting:
            approval.status = "rejected"
            approval.decision_note = "Replaced by a newer edit."


def briefs_for_posts(db: Session, tenant_id: UUID, post_ids: set[str]) -> dict[str, dict[str, str]]:
    if not post_ids:
        return {}
    approvals = db.scalars(
        select(AIApproval)
        .where(AIApproval.tenant_id == tenant_id, AIApproval.action_type == "social.publish")
        .order_by(AIApproval.created_at.desc())
        .limit(200)
    ).all()
    found: dict[str, dict[str, str]] = {}
    for approval in approvals:
        try:
            payload = json.loads(approval.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        brief = {
            "headline": approval.title.strip(),
            "keyword": str(payload.get("keyword") or "").strip(),
            "ranking_parameter": str(payload.get("ranking_parameter") or "").strip(),
            "snippet": str(payload.get("evidence") or "").strip(),
            "context": str(payload.get("why") or "").strip(),
        }
        for raw_id in payload.get("post_ids") or []:
            key = str(raw_id)
            if key in post_ids and key not in found:
                found[key] = brief
    return found


def reject_pending_posts(db: Session, *, tenant_id: UUID, approval: AIApproval, note: str) -> None:
    try:
        payload = json.loads(approval.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        return
    for raw_id in payload.get("post_ids") or []:
        row = db.get(SocialPost, UUID(str(raw_id)))
        if row is None or row.tenant_id != tenant_id or row.deleted_at is not None:
            continue
        if row.status != "pending_approval":
            continue
        row.status = "rejected"
        row.error = note.strip() or "Rejected before posting."


def publish_approved_posts(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    approval: AIApproval,
    payload_patch: dict | None = None,
) -> str:
    try:
        payload = json.loads(approval.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    replacement = ""
    if payload_patch and str(payload_patch.get("body") or "").strip():
        replacement = str(payload_patch["body"]).strip()[:_POST_TEXT_LIMIT]
    notes: list[str] = []
    for raw_id in payload.get("post_ids") or []:
        row = db.get(SocialPost, UUID(str(raw_id)))
        if row is None or row.tenant_id != tenant_id or row.deleted_at is not None:
            continue
        if row.status != "pending_approval":
            notes.append(f"{row.channel} already {row.status}")
            continue
        body = replacement or row.body
        links = _stored_links(row.extra_links)
        published = compose_post_text(body, links, row.link_url)
        status, result = _send(db, tenant_id, row.channel, published, row.link_url, row.image_url or row.video_url)
        row.body = body
        row.status = status
        row.provider = result.provider
        row.external_id = result.external_id
        row.permalink = resolved_permalink(
            row.channel,
            result.external_id,
            result.permalink,
            token=get_settings().meta_page_access_token if row.channel in {"facebook", "instagram"} else "",
        )
        row.is_mock = result.is_mock
        row.error = "" if result.ok else result.reason
        notes.append(f"{_CHANNEL_LABELS.get(row.channel, row.channel)}: {status}")
    if not notes:
        return "No posts were waiting for approval."
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="social.approved_publish",
        entity_type="ai_approval",
        entity_id=str(approval.id),
        after={"result": notes},
    )
    return "Posted " + ", ".join(notes)


def _stored_links(raw: str) -> list[dict[str, str]]:
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    links: list[dict[str, str]] = []
    for item in parsed:
        if isinstance(item, dict) and item.get("url"):
            links.append({"label": str(item.get("label") or ""), "url": str(item["url"])})
    return links


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
    row.permalink = resolved_permalink(
        row.channel,
        row.external_id,
        result.permalink or row.permalink,
        token=get_settings().meta_page_access_token if row.channel in {"facebook", "instagram"} else "",
    )
    row.is_mock = result.is_mock
    row.error = "" if result.ok else result.reason
    _audit_revision(db, tenant_id=tenant_id, actor_id=actor_id, row=row, before=before)
    return row


def _bytes_for_meta(db: Session, channel: str, body: str, image_url: str) -> bytes:
    if channel not in {"facebook", "instagram"}:
        return b""
    stored = _stored_media_bytes(db, image_url)
    if channel == "facebook":
        if stored and not instagram_can_fetch(image_url):
            return stored
        return b""
    if image_url.strip() and instagram_can_fetch(image_url):
        return b""
    if stored:
        return stored
    title = next((line.strip() for line in body.splitlines() if line.strip()), "Post")
    return draw_banner_png(title[:120])


def _stored_media_bytes(db: Session, image_url: str) -> bytes:
    marker = "/api/v1/public/media/"
    if marker not in (image_url or ""):
        return b""
    token = image_url.split(marker, 1)[1].split("?", 1)[0].strip("/")
    if not token:
        return b""
    try:
        data, _kind = read_social_image(db, token)
    except HTTPException:
        return b""
    return data


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
        result = publisher.publish(
            body=body,
            link_url=link_url,
            image_url=image_url,
            image_bytes=_bytes_for_meta(db, normalized, body, image_url),
            instagram=normalized == "instagram",
        )
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
        permalink=resolved_permalink(
            channel,
            result.external_id,
            result.permalink,
            token=get_settings().meta_page_access_token if channel in {"facebook", "instagram"} else "",
        ),
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
