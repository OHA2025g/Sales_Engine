from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import CompletionResult, get_llm_provider
from app.models.content import ContentDraft, SellerProfile
from app.models.lifecycle import Campaign, Product
from app.providers.ads import get_ads_provider
from app.services.audit import write_audit
from app.services.social import publish_post

POST_SLOTS = (
    ("LINKEDIN_POST", "linkedin", "post"),
    ("FACEBOOK_POST", "facebook", "post"),
    ("INSTAGRAM_POST", "instagram", "post"),
)
AD_CHANNELS = {"linkedin", "instagram"}
SENT_STATUSES = ("published", "paused", "mock")


def get_profile(db: Session, tenant_id: UUID) -> SellerProfile | None:
    return db.scalar(
        select(SellerProfile).where(SellerProfile.tenant_id == tenant_id, SellerProfile.deleted_at.is_(None))
    )


def save_profile(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    company_name: str,
    summary: str,
    audience: str,
    website: str,
    proof: str,
    capture_url: str,
) -> SellerProfile:
    row = get_profile(db, tenant_id)
    if row is None:
        row = SellerProfile(tenant_id=tenant_id, created_by=actor_id)
        db.add(row)
    row.company_name = company_name.strip()
    row.summary = summary.strip()
    row.audience = audience.strip()
    row.website = website.strip()
    row.proof = proof.strip()
    row.capture_url = capture_url.strip()
    row.updated_by = actor_id
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="content.profile",
        entity_type="seller_profile",
        entity_id=str(row.id),
        after={"company_name": row.company_name},
    )
    return row


def list_products(db: Session, tenant_id: UUID) -> list[Product]:
    return list(
        db.scalars(select(Product).where(Product.tenant_id == tenant_id, Product.deleted_at.is_(None)).order_by(Product.name)).all()
    )


def create_catalog_product(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    sku: str,
    name: str,
    description: str,
    kind: str,
    list_price: Decimal,
    currency: str,
) -> Product:
    row = Product(
        tenant_id=tenant_id,
        created_by=actor_id,
        sku=sku.strip(),
        name=name.strip(),
        description=description.strip(),
        kind=kind.strip() or "subscription",
        list_price=list_price,
        currency=currency.strip() or "INR",
    )
    db.add(row)
    db.flush()
    return row


def update_product_description(db: Session, *, tenant_id: UUID, product_id: UUID, description: str) -> Product:
    row = db.scalar(select(Product).where(Product.tenant_id == tenant_id, Product.id == product_id, Product.deleted_at.is_(None)))
    if row is None:
        raise HTTPException(status_code=404, detail="Product was not found.")
    row.description = description.strip()
    db.flush()
    return row


def list_drafts(db: Session, tenant_id: UUID) -> list[ContentDraft]:
    return list(
        db.scalars(
            select(ContentDraft)
            .where(ContentDraft.tenant_id == tenant_id, ContentDraft.deleted_at.is_(None))
            .order_by(ContentDraft.created_at.desc())
        ).all()
    )


def update_draft(
    db: Session,
    *,
    tenant_id: UUID,
    draft_id: UUID,
    headline: str,
    body: str,
    cta: str,
    image_url: str,
) -> ContentDraft:
    row = _draft(db, tenant_id, draft_id)
    if row.status in {"published", "paused", "mock"}:
        raise HTTPException(status_code=409, detail="This draft was already sent.")
    row.headline = headline.strip()
    row.body = body.strip()
    row.cta = cta.strip()
    row.image_url = image_url.strip()
    db.flush()
    return row


def generate_drafts(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    product_id: UUID,
    ad_channel: str,
    brief: str = "",
) -> list[ContentDraft]:
    network = ad_channel.strip().lower()
    note = brief.strip()[:2000]
    if network not in AD_CHANNELS:
        raise HTTPException(status_code=422, detail="Ad channel must be linkedin or instagram.")
    profile = get_profile(db, tenant_id)
    if profile is None or not profile.company_name.strip() or not profile.summary.strip():
        raise HTTPException(status_code=422, detail="Save a company name and what you sell before generating.")
    product = db.scalar(select(Product).where(Product.tenant_id == tenant_id, Product.id == product_id, Product.deleted_at.is_(None)))
    if product is None:
        raise HTTPException(status_code=404, detail="Product was not found.")
    if not product.description.strip():
        raise HTTPException(status_code=422, detail="Add a product description before generating. Empty copy is not invented.")
    sent = _already_sent(db, tenant_id, product.id)
    prompt = _prompt(profile, product, network, note, sent)
    system = _system_prompt()
    result = None
    failure = ""
    for _attempt in range(2):
        try:
            result = get_llm_provider(db, tenant_id).complete(prompt, system=system)
            break
        except (httpx.HTTPError, RuntimeError) as exc:
            quota = _quota_failure(exc)
            if quota:
                failure = quota
                break
            result = None
    if result is None:
        slots = [*POST_SLOTS, ("AD", network, "ad")]
        rows = [
            _blank(
                tenant_id,
                actor_id,
                product.id,
                channel,
                kind,
                failure or "Gemini did not return a draft. Nothing was written or published.",
                False,
                note,
            )
            for _key, channel, kind in slots
        ]
    else:
        rows = _rows_from_completion(
            result,
            tenant_id=tenant_id,
            actor_id=actor_id,
            product=product,
            profile=profile,
            ad_channel=network,
            brief=note,
        )
    for row in rows:
        db.add(row)
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="content.generate",
        entity_type="content_draft",
        entity_id=str(product.id),
        after={"count": len(rows), "ad_channel": network},
        actor_type="ai" if result is not None and not result.is_mock else "human",
    )
    return rows


def publish_draft(db: Session, *, tenant_id: UUID, actor_id: UUID, draft_id: UUID) -> ContentDraft:
    row = _draft(db, tenant_id, draft_id)
    if row.status in {"published", "paused", "mock"}:
        raise HTTPException(status_code=409, detail="This draft was already sent.")
    if row.kind == "ad":
        return _publish_ad(db, tenant_id=tenant_id, actor_id=actor_id, draft=row)
    return _publish_post(db, tenant_id=tenant_id, actor_id=actor_id, draft=row)


def _draft(db: Session, tenant_id: UUID, draft_id: UUID) -> ContentDraft:
    row = db.scalar(
        select(ContentDraft).where(
            ContentDraft.tenant_id == tenant_id,
            ContentDraft.id == draft_id,
            ContentDraft.deleted_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Draft was not found.")
    return row


def _already_sent(db: Session, tenant_id: UUID, product_id: UUID) -> list[ContentDraft]:
    return list(
        db.scalars(
            select(ContentDraft)
            .where(
                ContentDraft.tenant_id == tenant_id,
                ContentDraft.product_id == product_id,
                ContentDraft.deleted_at.is_(None),
                ContentDraft.status.in_(SENT_STATUSES),
            )
            .order_by(ContentDraft.created_at.desc())
            .limit(12)
        ).all()
    )


def draft_email_from_facts(db: Session, tenant_id: UUID, facts: str) -> str:
    source = facts.strip()
    if not source:
        return ""
    try:
        result = get_llm_provider(db, tenant_id).complete(
            "Write the email body from these facts only. Do not add a price, customer, or claim that is not written here.\n\n"
            + source,
            system="You write one plain-text sales email body. No subject line. No markdown.",
        )
    except (httpx.HTTPError, RuntimeError):
        return source
    text = (result.text or "").strip()
    if not text or result.is_mock or "NOT_CONFIGURED" in text:
        return source
    return text


def _quota_failure(exc: Exception) -> str:
    text = str(exc).strip()
    lowered = text.lower()
    if "quota" not in lowered and "retry in" not in lowered and "rate-limit" not in lowered and "rate limit" not in lowered:
        return ""
    if "Nothing was written or published." not in text:
        text = f"{text} Nothing was written or published."
    return text[:500]


def _system_prompt() -> str:
    return (
        "You write the complete post and ad yourself. Use only the facts in the user message. "
        "Do not invent prices, discounts, customer counts, awards, or testimonials. "
        "Do not repeat a headline or offer that was already sent. "
        "Do not say the post or ad has been published."
    )


def _prompt(profile: SellerProfile, product: Product, ad_channel: str, brief: str, sent: list[ContentDraft]) -> str:
    if product.list_price and Decimal(str(product.list_price)) > 0:
        price = f"List price is {product.currency} {product.list_price}. Repeat this price only. Do not discount it."
    else:
        price = "No price is on file. Do not mention a price, discount, or customer count."
    proof = profile.proof.strip() or "No proof is on file. Do not invent a customer story or a statistic."
    link = profile.capture_url.strip() or "No capture link is on file. Tell the reader to reply. Do not invent a URL."
    angle = (
        f"Optional note from the operator. Follow it when it fits the facts: {brief}"
        if brief
        else "The operator left no note. Choose the angle from the company and the product."
    )
    return (
        f"Company: {profile.company_name}\n"
        f"What the company does: {profile.summary}\n"
        f"Who they sell to: {profile.audience or 'not specified'}\n"
        f"Website: {profile.website or 'not specified'}\n"
        f"Proof: {proof}\n"
        f"Product: {product.name}\n"
        f"Product description: {product.description}\n"
        f"{price}\n"
        f"Capture link to include exactly when a link is on file: {link}\n"
        f"Ad network for the ad section: {ad_channel}\n"
        f"{angle}\n"
        f"{_sent_block(sent)}\n\n"
        "Write the full headline, body, and call to action yourself. Do not leave a placeholder.\n"
        "Return exactly these sections and no other text:\n"
        "===LINKEDIN_POST===\nheadline: \nbody: \ncta: \n"
        "===FACEBOOK_POST===\nheadline: \nbody: \ncta: \n"
        "===INSTAGRAM_POST===\nheadline: \nbody: \ncta: \n"
        "===AD===\nheadline: \nbody: \ncta: \n"
        "The body should make a clear offer and tell the reader how to connect. "
        "If a capture link is on file, put that exact link in the body."
    )


def _sent_block(sent: list[ContentDraft]) -> str:
    if not sent:
        return "Nothing has been sent for this product yet."
    lines = ["Already sent. Write a new angle. Do not repeat these headlines or the same body:"]
    for row in sent:
        snippet = " ".join(row.body.split())[:240]
        lines.append(f"- {row.channel} {row.kind} [{row.status}] {row.headline}: {snippet}")
    return "\n".join(lines)


def _rows_from_completion(
    result: CompletionResult,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    product: Product,
    profile: SellerProfile,
    ad_channel: str,
    brief: str,
) -> list[ContentDraft]:
    slots = [*POST_SLOTS, ("AD", ad_channel, "ad")]
    if (not result.is_mock) and "NOT_CONFIGURED" in result.text:
        return [
            _blank(
                tenant_id,
                actor_id,
                product.id,
                channel,
                kind,
                "NOT_CONFIGURED. Set GEMINI_API_KEY. Nothing was written or published.",
                False,
                brief,
            )
            for _key, channel, kind in slots
        ]
    parsed = _parse_sections(result.text)
    rows: list[ContentDraft] = []
    for key, channel, kind in slots:
        section = parsed.get(key)
        destination = _destination(profile.capture_url, channel, kind, product.name)
        if not section or not section.get("body"):
            rows.append(
                _blank(
                    tenant_id,
                    actor_id,
                    product.id,
                    channel,
                    kind,
                    "The draft could not be read. Nothing was published.",
                    result.is_mock,
                    brief,
                )
            )
            continue
        rows.append(
            ContentDraft(
                tenant_id=tenant_id,
                created_by=actor_id,
                product_id=product.id,
                channel=channel,
                kind=kind,
                headline=section.get("headline", "")[:300],
                body=section.get("body", ""),
                cta=section.get("cta", "")[:300],
                destination_url=destination,
                brief=brief,
                status="draft",
                is_mock=result.is_mock,
            )
        )
    return rows


def _blank(
    tenant_id: UUID,
    actor_id: UUID,
    product_id: UUID,
    channel: str,
    kind: str,
    error: str,
    is_mock: bool,
    brief: str,
) -> ContentDraft:
    return ContentDraft(
        tenant_id=tenant_id,
        created_by=actor_id,
        product_id=product_id,
        channel=channel,
        kind=kind,
        brief=brief,
        status="failed",
        error=error,
        is_mock=is_mock,
    )


def _parse_sections(text: str) -> dict[str, dict[str, str]]:
    chunks = text.split("===")
    sections: dict[str, dict[str, str]] = {}
    index = 1
    while index < len(chunks) - 1:
        key = chunks[index].strip()
        body = chunks[index + 1]
        index += 2
        if not key:
            continue
        sections[key] = _parse_fields(body)
    return sections


def _parse_fields(block: str) -> dict[str, str]:
    headline = ""
    cta = ""
    body_lines: list[str] = []
    mode = ""
    for line in block.splitlines():
        lowered = line.lower()
        if lowered.startswith("headline:"):
            headline = line.split(":", 1)[1].strip()
            mode = "body"
            continue
        if lowered.startswith("cta:"):
            cta = line.split(":", 1)[1].strip()
            mode = "cta"
            continue
        if lowered.startswith("body:"):
            first = line.split(":", 1)[1].strip()
            body_lines = [first] if first else []
            mode = "body"
            continue
        if mode == "body":
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return {"headline": headline, "body": body, "cta": cta}


def _destination(capture_url: str, channel: str, kind: str, product_name: str) -> str:
    raw = capture_url.strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["utm_source"] = channel
    query["utm_medium"] = "paid" if kind == "ad" else "social"
    query["utm_campaign"] = product_name.strip().replace(" ", "-")[:80]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _publish_post(db: Session, *, tenant_id: UUID, actor_id: UUID, draft: ContentDraft) -> ContentDraft:
    if draft.channel == "instagram" and not draft.image_url.strip():
        draft.status = "failed"
        draft.error = "Instagram posts require a public image URL. Nothing was published."
        db.flush()
        return draft
    text = "\n\n".join(part.strip() for part in (draft.headline, draft.body, draft.cta) if part.strip())
    posted = publish_post(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        channel=draft.channel,
        body=text or draft.body,
        link_url=draft.destination_url,
        image_url=draft.image_url,
    )
    draft.social_post_id = posted.id
    draft.provider = posted.provider
    draft.external_id = posted.external_id
    draft.is_mock = posted.is_mock
    if posted.status == "published":
        draft.status = "published"
        draft.error = ""
    elif posted.status == "mock":
        draft.status = "mock"
        draft.error = ""
    else:
        draft.status = "failed"
        draft.error = posted.error or "The post was not published."
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="content.publish",
        entity_type="content_draft",
        entity_id=str(draft.id),
        after={"status": draft.status, "channel": draft.channel},
    )
    db.flush()
    return draft


def _publish_ad(db: Session, *, tenant_id: UUID, actor_id: UUID, draft: ContentDraft) -> ContentDraft:
    from app.services.dispatcher import _channel_blocked
    from app.services.revenue_ledger import approved_ad_budget

    product = None
    if draft.product_id is not None:
        product = db.get(Product, draft.product_id)
    blocked = _channel_blocked(db, tenant_id, "ads.launch")
    if blocked:
        draft.status = "blocked"
        draft.error = blocked
        db.flush()
        return draft
    plan = approved_ad_budget(db, tenant_id=tenant_id, channel=draft.channel, product_id=draft.product_id)
    if plan is None:
        draft.status = "failed"
        draft.error = "Approved marketing budget is required. Product price is not an ad budget."
        db.flush()
        return draft
    budget = Decimal(str(plan.budget)) - Decimal(str(plan.spent or 0))
    name = (draft.headline or (product.name if product else "Content ad"))[:160]
    campaign = Campaign(
        tenant_id=tenant_id,
        created_by=actor_id,
        name=name,
        channel=draft.channel,
        status="draft",
        objective="pipeline",
        budget=budget,
        notes=draft.body[:2000],
    )
    db.add(campaign)
    db.flush()
    provider = get_ads_provider(draft.channel, db, tenant_id)
    result = provider.create_campaign(name=name, objective="pipeline", budget=budget)
    draft.campaign_id = campaign.id
    draft.provider = result.provider
    draft.is_mock = result.is_mock
    if result.ok and result.external_id and result.provider_status == "PAUSED":
        campaign.status = "paused"
        campaign.external_campaign_id = result.external_id
        campaign.provider = result.provider
        campaign.provider_status = "PAUSED"
        draft.status = "paused"
        draft.external_id = result.external_id
        draft.error = ""
    else:
        draft.status = "failed"
        draft.error = result.reason or "Campaign was not created. Nothing was activated."
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="content.publish",
        entity_type="content_draft",
        entity_id=str(draft.id),
        after={"status": draft.status, "channel": draft.channel, "provider_status": campaign.provider_status},
    )
    db.flush()
    return draft
