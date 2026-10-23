"""One product operating plan: audience, calendar, authorization, publication, outcomes.

Copy comes from stored company knowledge. Metrics stay absent until a provider
returns them. A sandbox or localhost image never becomes a live activation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.autonomy import AutonomousRun
from app.models.content import SellerProfile
from app.models.crm import ICP, Lead, Opportunity
from app.models.funnel import PublicFormKey
from app.models.lifecycle import Campaign, Product
from app.models.operating_plan import CreativeVersion, OperatingPlan
from app.models.social import SocialPost
from app.providers.social import MockSocialPublisher, get_social_publisher, instagram_can_fetch
from app.services.audit import write_audit
from app.services.demo_guard import external_execution_block
from app.services.discovery import run_discovery
from app.services.effects import EffectAttempt, ReconciledEffect, execute_external_effect
from app.services.public_forms import form_key_url
from app.services.social import publish_post

MINIMUM_IMPRESSIONS = 100


def _latest_plan(db: Session, tenant_id: UUID) -> OperatingPlan | None:
    """The open plan, or the newest plan when none is open.

    An open plan stays the target after a later product is created. A closed
    plan from the same second must not hide the plan that was just started.
    """
    shared = (OperatingPlan.tenant_id == tenant_id, OperatingPlan.deleted_at.is_(None))
    opened = db.scalar(
        select(OperatingPlan)
        .where(*shared, OperatingPlan.status.in_(["running", "blocked", "paused"]))
        .order_by(OperatingPlan.created_at.desc(), OperatingPlan.id.desc())
    )
    if opened is not None:
        return opened
    return db.scalar(
        select(OperatingPlan).where(*shared).order_by(OperatingPlan.created_at.desc(), OperatingPlan.id.desc())
    )


def _product_choices(db: Session, tenant_id: UUID) -> list[dict]:
    rows = db.scalars(
        select(Product).where(Product.tenant_id == tenant_id, Product.deleted_at.is_(None)).order_by(Product.name.asc())
    ).all()
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "sku": row.sku,
            "kind": row.kind,
            "list_price": str(row.list_price),
            "currency": row.currency,
        }
        for row in rows
    ]


def _load_snapshot(plan: OperatingPlan) -> dict:
    try:
        loaded = json.loads(plan.context_snapshot or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _snapshot_payload(product: Product, audience: str, profile: SellerProfile | None) -> dict:
    return {
        "product_id": str(product.id),
        "sku": product.sku,
        "name": product.name.strip(),
        "kind": product.kind,
        "list_price": str(product.list_price),
        "currency": product.currency,
        "description": product.description.strip(),
        "audience": audience,
        "seller_summary": profile.summary.strip() if profile is not None and profile.summary else "",
    }


def _freeze_context(db: Session, plan: OperatingPlan) -> dict:
    current = _load_snapshot(plan)
    if str(current.get("description") or "").strip() and str(current.get("name") or "").strip():
        return current
    if plan.product_id is None:
        return current
    product = db.get(Product, plan.product_id)
    if product is None or product.tenant_id != plan.tenant_id or product.deleted_at is not None:
        return current
    profile = db.scalar(select(SellerProfile).where(SellerProfile.tenant_id == plan.tenant_id, SellerProfile.deleted_at.is_(None)))
    audience = plan.audience.strip() or _audience(db, plan.tenant_id)
    payload = _snapshot_payload(product, audience, profile)
    plan.context_snapshot = json.dumps(payload)
    if not plan.audience.strip():
        plan.audience = audience
    return payload


def _audience(db: Session, tenant_id: UUID) -> str:
    icp = db.scalar(select(ICP).where(ICP.tenant_id == tenant_id, ICP.deleted_at.is_(None), ICP.is_default.is_(True)))
    if icp is None:
        icp = db.scalar(select(ICP).where(ICP.tenant_id == tenant_id, ICP.deleted_at.is_(None)).order_by(ICP.created_at.asc()))
    profile = db.scalar(select(SellerProfile).where(SellerProfile.tenant_id == tenant_id, SellerProfile.deleted_at.is_(None)))
    parts = []
    if icp is not None:
        parts.extend(part.strip() for part in (icp.name, icp.industries, icp.geographies, icp.personas) if part and part.strip())
    if profile is not None and profile.audience.strip():
        parts.append(profile.audience.strip())
    return " · ".join(dict.fromkeys(parts))


def _form(db: Session, tenant_id: UUID) -> PublicFormKey | None:
    return db.scalar(
        select(PublicFormKey)
        .where(PublicFormKey.tenant_id == tenant_id, PublicFormKey.status == "active", PublicFormKey.deleted_at.is_(None))
        .order_by(PublicFormKey.created_at.desc())
    )


def _public_url(url: str) -> bool:
    folded = (url or "").casefold()
    return bool(folded) and "localhost" not in folded and "127.0.0.1" not in folded


def _hash(headline: str, body: str, image_url: str) -> str:
    material = f"{headline}|{body}|{image_url}".strip()
    return hashlib.sha256(material.encode()).hexdigest()


def _detail(plan: OperatingPlan, message: str) -> dict:
    return {
        "plan_id": str(plan.id),
        "status": plan.status,
        "next_action": plan.next_action,
        "blocker": plan.blocker,
        "detail": message,
    }


def start_operating_plan(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    channel: str = "linkedin",
    product_id: UUID | None = None,
) -> dict:
    existing = _latest_plan(db, tenant_id)
    if existing is not None and existing.status in {"running", "blocked", "paused"}:
        _freeze_context(db, existing)
        return _detail(existing, "The operating plan is already open. Its selected product was kept.")
    choices = _product_choices(db, tenant_id)
    if product_id is None:
        return {
            "plan_id": "",
            "status": "blocked",
            "next_action": "choose_product",
            "blocker": "Choose a product and its offer.",
            "detail": "Choose a product and its offer. A new product was not selected automatically.",
            "products": choices,
        }
    product = db.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.id == product_id, Product.deleted_at.is_(None))
    )
    if product is None:
        return {
            "plan_id": "",
            "status": "blocked",
            "next_action": "choose_product",
            "blocker": "That product is not in this workspace.",
            "detail": "That product is not in this workspace.",
            "products": choices,
        }
    audience = _audience(db, tenant_id)
    profile = db.scalar(select(SellerProfile).where(SellerProfile.tenant_id == tenant_id, SellerProfile.deleted_at.is_(None)))
    missing_copy = not product.description.strip()
    missing_audience = not audience
    plan = OperatingPlan(
        tenant_id=tenant_id,
        created_by=actor_id,
        channel=(channel or "linkedin").strip().lower()[:20] or "linkedin",
        product_id=product.id,
        audience=audience,
        context_snapshot=json.dumps(_snapshot_payload(product, audience, profile)),
        status="blocked" if missing_copy or missing_audience else "running",
        research_limit=5,
        next_action="save_product_knowledge" if missing_copy else ("save_audience" if missing_audience else "research_prospects"),
        blocker="" if not missing_copy and not missing_audience else "Save the product description and the ICP audience before research or content.",
    )
    db.add(plan)
    db.flush()
    if product is not None:
        campaign = Campaign(
            tenant_id=tenant_id,
            created_by=actor_id,
            name=product.name[:160],
            channel=plan.channel,
            status="draft",
            objective="pipeline",
            notes=f"Attribution campaign for operating plan {plan.id}. Not launched.",
        )
        db.add(campaign)
        db.flush()
        plan.campaign_id = campaign.id
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="operating_plan.start",
        entity_type="operating_plan",
        entity_id=str(plan.id),
        after={"status": plan.status, "channel": plan.channel, "product_id": str(plan.product_id or "")},
    )
    offer = f"{product.name} · {product.kind} · {product.list_price} {product.currency}"
    return {**_detail(plan, plan.blocker or f"Operating plan started for {offer}."), "products": choices}


def research_prospects(db: Session, *, tenant_id: UUID, actor_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    if plan is None:
        started = start_operating_plan(db, tenant_id=tenant_id, actor_id=actor_id)
        plan = _latest_plan(db, tenant_id)
        if plan is None:
            return started
    if plan.status == "paused":
        return _detail(plan, "The operating plan is paused.")
    if plan.blocker:
        return _detail(plan, plan.blocker)
    if plan.research_runs >= plan.research_limit:
        plan.status = "blocked"
        plan.blocker = f"Research limit of {plan.research_limit} runs is reached."
        plan.next_action = "resolve_blocker"
        return _detail(plan, plan.blocker)
    plan.research_runs += 1
    result = run_discovery(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        search_query=plan.audience,
        correlation_id=f"plan:{plan.id}",
    )
    plan.next_action = "generate_draft"
    message = f"Research run {plan.research_runs} of {plan.research_limit}. Created {result.get('created', 0)}. {result.get('reason', '')}".strip()
    if result.get("failure_class") or (result.get("reason") and not result.get("connected") and not result.get("is_mock")):
        plan.status = "blocked"
        plan.blocker = str(result.get("reason") or "Discovery failed.")
        plan.next_action = "resolve_blocker"
        message = plan.blocker
    return {**_detail(plan, message), "discovery": result}


def generate_draft(db: Session, *, tenant_id: UUID, actor_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    if plan is None or plan.product_id is None:
        return {"detail": "Start the operating plan from a saved product first.", "status": "blocked", "next_action": "start_operating_plan", "blocker": "No operating plan.", "plan_id": ""}
    snapshot = _freeze_context(db, plan)
    name = str(snapshot.get("name") or "").strip()
    description = str(snapshot.get("description") or "").strip()
    if not name or not description:
        plan.status = "blocked"
        plan.blocker = "The selected product has no description. Content was not invented."
        plan.next_action = "save_product_knowledge"
        return _detail(plan, plan.blocker)
    if not plan.audience.strip():
        plan.status = "blocked"
        plan.blocker = "No ICP or seller audience is saved. The calendar was not invented."
        plan.next_action = "save_audience"
        return _detail(plan, plan.blocker)
    form = _form(db, tenant_id)
    plan.form_key_id = form.id if form is not None else None
    link = form_key_url(form) if form is not None else ""
    if link and plan.campaign_id is not None:
        join = "&" if "?" in link else "?"
        link = f"{link}{join}utm_source={plan.channel}&utm_medium=social&utm_campaign={plan.id}"
    seller = str(snapshot.get("seller_summary") or "").strip()
    knowledge = "\n\n".join(part for part in (name, description, seller) if part)
    headline = name[:300]
    body = f"{knowledge}\n\nFor {plan.audience}."
    if plan.channel == "instagram" and link:
        body = f"{link}\n\n{body}"
    elif link:
        body = f"{body}\n\n{link}"
    number = int(
        db.scalar(
            select(func.max(CreativeVersion.version_number)).where(
                CreativeVersion.tenant_id == tenant_id,
                CreativeVersion.plan_id == plan.id,
                CreativeVersion.deleted_at.is_(None),
            )
        )
        or 0
    ) + 1
    row = CreativeVersion(
        tenant_id=tenant_id,
        created_by=actor_id,
        plan_id=plan.id,
        channel=plan.channel,
        version_number=number,
        headline=headline,
        body=body.strip(),
        content_hash=_hash(headline, body.strip(), ""),
        status="draft",
    )
    db.add(row)
    db.flush()
    plan.status = "running"
    plan.blocker = ""
    plan.next_action = "review_pending_version"
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="operating_plan.draft",
        entity_type="creative_version",
        entity_id=str(row.id),
        after={"version": number, "channel": plan.channel},
    )
    return {**_detail(plan, f"Draft version {number} is waiting for review."), "version_id": str(row.id), "version": number}


def review_versions(db: Session, tenant_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    if plan is None:
        return {"versions": [], "detail": "No operating plan is open.", "next_action": "start_operating_plan"}
    rows = db.scalars(
        select(CreativeVersion)
        .where(CreativeVersion.tenant_id == tenant_id, CreativeVersion.plan_id == plan.id, CreativeVersion.deleted_at.is_(None))
        .order_by(CreativeVersion.version_number.asc())
    ).all()
    return {
        "plan_id": str(plan.id),
        "next_action": plan.next_action,
        "detail": "Pending versions stay drafts until they are authorized.",
        "versions": [
            {
                "id": str(row.id),
                "version": row.version_number,
                "status": row.status,
                "channel": row.channel,
                "headline": row.headline,
                "scheduled_for": row.scheduled_for.isoformat() if row.scheduled_for else "",
                "outcome": row.outcome,
            }
            for row in rows
        ],
    }


def _version(db: Session, tenant_id: UUID, version_id: UUID) -> CreativeVersion | None:
    return db.scalar(
        select(CreativeVersion).where(
            CreativeVersion.tenant_id == tenant_id,
            CreativeVersion.id == version_id,
            CreativeVersion.deleted_at.is_(None),
        )
    )


def authorize_version(db: Session, *, tenant_id: UUID, actor_id: UUID, version_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    row = _version(db, tenant_id, version_id)
    if plan is None or row is None or row.plan_id != plan.id:
        return {"detail": "That version is not on the open operating plan.", "status": "blocked", "next_action": "review_pending_version", "blocker": "", "plan_id": str(plan.id) if plan else ""}
    if row.status != "draft":
        return _detail(plan, f"Version {row.version_number} is {row.status} and was not changed.")
    row.status = "authorized"
    row.content_hash = _hash(row.headline, row.body, row.image_url)
    plan.next_action = "preview_schedule"
    plan.blocker = ""
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="operating_plan.authorize",
        entity_type="creative_version",
        entity_id=str(row.id),
        after={"version": row.version_number, "content_hash": row.content_hash},
    )
    return _detail(plan, f"Version {row.version_number} is authorized and immutable.")


def revise_version(db: Session, *, tenant_id: UUID, actor_id: UUID, version_id: UUID, body: str) -> dict:
    plan = _latest_plan(db, tenant_id)
    row = _version(db, tenant_id, version_id)
    if plan is None or row is None:
        return {"detail": "That version was not found.", "status": "blocked", "next_action": "review_pending_version", "blocker": "", "plan_id": ""}
    text = body.strip()
    if not text or text == row.body:
        return _detail(plan, "No material edit was saved.")
    if row.status == "draft":
        row.body = text
        row.content_hash = _hash(row.headline, row.body, row.image_url)
        return _detail(plan, f"Draft version {row.version_number} was updated.")
    number = row.version_number + 1
    successor = CreativeVersion(
        tenant_id=tenant_id,
        created_by=actor_id,
        plan_id=plan.id,
        channel=row.channel,
        version_number=number,
        headline=row.headline,
        body=text,
        image_url=row.image_url,
        content_hash=_hash(row.headline, text, row.image_url),
        status="draft",
    )
    db.add(successor)
    db.flush()
    plan.next_action = "review_pending_version"
    return {**_detail(plan, f"Version {row.version_number} stayed authorized. Version {number} needs review."), "version_id": str(successor.id)}


def preview_schedule(db: Session, tenant_id: UUID) -> dict:
    reviewed = review_versions(db, tenant_id)
    scheduled = [row for row in reviewed.get("versions", []) if row["status"] in {"authorized", "scheduled", "published"}]
    return {**reviewed, "detail": "Authorized versions can be scheduled. Drafts cannot.", "scheduled": scheduled}


def schedule_version(db: Session, *, tenant_id: UUID, actor_id: UUID, version_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    row = _version(db, tenant_id, version_id)
    if plan is None or row is None:
        return {"detail": "That version was not found.", "status": "blocked", "next_action": "review_pending_version", "blocker": "", "plan_id": ""}
    if row.status != "authorized":
        return _detail(plan, f"Version {row.version_number} is {row.status}. Only an authorized version can be scheduled.")
    row.status = "scheduled"
    row.scheduled_for = datetime.now(UTC) + timedelta(minutes=5)
    plan.next_action = "publish_scheduled"
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="operating_plan.schedule",
        entity_type="creative_version",
        entity_id=str(row.id),
        after={"scheduled_for": row.scheduled_for.isoformat()},
    )
    return _detail(plan, f"Version {row.version_number} is scheduled. Nothing has been published.")


def _blocked_publication(plan: OperatingPlan, message: str) -> dict:
    plan.status = "blocked"
    plan.blocker = message
    plan.next_action = "resolve_blocker"
    return _detail(plan, message)


def publish_scheduled(db: Session, *, tenant_id: UUID, actor_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    if plan is None:
        return {"detail": "No operating plan is open.", "status": "blocked", "next_action": "start_operating_plan", "blocker": "", "plan_id": ""}
    if plan.status == "paused":
        return _detail(plan, "A paused plan does not publish.")
    row = db.scalar(
        select(CreativeVersion)
        .where(
            CreativeVersion.tenant_id == tenant_id,
            CreativeVersion.plan_id == plan.id,
            CreativeVersion.status == "scheduled",
            CreativeVersion.deleted_at.is_(None),
        )
        .order_by(CreativeVersion.version_number.asc())
    )
    if row is None:
        return _detail(plan, "No scheduled version is waiting.")
    if _hash(row.headline, row.body, row.image_url) != row.content_hash:
        return _blocked_publication(plan, "The scheduled copy does not match the authorized version. Nothing was published.")
    blocked = external_execution_block(
        db,
        tenant_id=tenant_id,
        action="social.publish",
        target_id=str(row.id),
        channel=row.channel,
    )
    if blocked:
        return _blocked_publication(plan, blocked)
    if row.channel == "instagram" and not instagram_can_fetch(row.image_url):
        return _blocked_publication(plan, "Instagram cannot fetch an image hosted on this machine. Nothing was published.")
    form = _form(db, tenant_id)
    link = form_key_url(form) if form is not None else ""
    publisher = get_social_publisher(row.channel)
    if not isinstance(publisher, MockSocialPublisher) and not _public_url(link):
        return _blocked_publication(plan, "The capture form is not publicly reachable. The live publisher was not called.")
    if form is None:
        return _blocked_publication(plan, "No active capture form is attached. Nothing was published.")
    run = AutonomousRun(
        tenant_id=tenant_id,
        created_by=actor_id,
        status="running",
        trigger="manual",
        workflow="marketing",
        trigger_event=f"plan:{plan.id}"[:80],
        summary=f"Publish version {row.version_number}",
    )
    db.add(run)
    db.flush()

    def call() -> EffectAttempt:
        posted = publish_post(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            channel=row.channel,
            body="\n\n".join(part for part in (row.headline, row.body) if part.strip()),
            link_url=link,
            image_url=row.image_url,
            form_key_id=form.id,
        )
        row.social_post_id = posted.id
        row.provider_ref = posted.external_id or ""
        row.permalink = posted.permalink or ""
        if posted.external_id and posted.status in {"published", "mock"}:
            return EffectAttempt(accepted=True, provider_id=posted.external_id)
        if posted.status in {"failed", "blocked"}:
            return EffectAttempt(failed=True, failure_class="PERMANENT")
        return EffectAttempt()

    def reconcile(effect) -> ReconciledEffect:
        _ = effect
        if row.social_post_id is None:
            return ReconciledEffect("unknown")
        posted = db.get(SocialPost, row.social_post_id)
        if posted is None:
            return ReconciledEffect("unknown")
        if posted.external_id and posted.status in {"published", "mock"}:
            row.provider_ref = posted.external_id
            row.permalink = posted.permalink or row.permalink
            return ReconciledEffect("confirmed", posted.external_id)
        if posted.status in {"failed", "blocked"}:
            return ReconciledEffect("confirmed_failure")
        return ReconciledEffect("unknown")

    effect = execute_external_effect(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        run=run,
        action="social.publish",
        channel=row.channel,
        target_id=str(row.id),
        content_version=row.content_hash,
        grant_id="",
        call=call,
        reconcile=reconcile,
    )
    row.outcome = effect.outcome
    if effect.provider_ref:
        row.provider_ref = effect.provider_ref
    if effect.outcome == "confirmed":
        row.status = "published"
        plan.next_action = "review_outcomes"
        plan.blocker = ""
        run.status = "completed"
    elif effect.outcome == "confirmed_failure":
        plan.status = "blocked"
        plan.blocker = "Publication failed. The provider id was not confirmed."
        plan.next_action = "resolve_blocker"
        run.status = "blocked"
    else:
        plan.next_action = "reconcile_publication"
        plan.blocker = ""
        run.status = "running"
    run.finished_at = datetime.now(UTC) if effect.outcome != "unknown" else None
    return _detail(plan, f"Publication outcome is {effect.outcome or 'unknown'}.")


def publication_evidence(db: Session, tenant_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    if plan is None:
        return {"detail": "No operating plan is open.", "evidence": []}
    rows = db.scalars(
        select(CreativeVersion).where(
            CreativeVersion.tenant_id == tenant_id,
            CreativeVersion.plan_id == plan.id,
            CreativeVersion.deleted_at.is_(None),
        )
    ).all()
    return {
        "detail": "Provider ids and permalinks are shown only when the publisher returned them.",
        "evidence": [
            {
                "version": row.version_number,
                "outcome": row.outcome or "unavailable",
                "provider_ref": row.provider_ref,
                "permalink": row.permalink,
            }
            for row in rows
            if row.outcome or row.provider_ref
        ],
    }


def record_metrics(db: Session, *, tenant_id: UUID, version_id: UUID, metrics: dict | None) -> dict:
    row = _version(db, tenant_id, version_id)
    plan = _latest_plan(db, tenant_id)
    if row is None or plan is None:
        return {"detail": "That version was not found.", "optimization": "insufficient_evidence"}
    if not metrics:
        row.metrics_json = ""
        return {"detail": "The provider did not supply metrics. They stay unavailable.", "optimization": "insufficient_evidence", "impressions": None, "budget_change": None}
    stored = {key: metrics[key] for key in ("impressions", "clicks", "spend") if key in metrics and metrics[key] is not None}
    row.metrics_json = json.dumps(stored)
    impressions = stored.get("impressions")
    if not isinstance(impressions, int) or impressions < MINIMUM_IMPRESSIONS:
        return {
            "detail": f"Optimization needs at least {MINIMUM_IMPRESSIONS} provider impressions.",
            "optimization": "insufficient_evidence",
            "impressions": impressions,
            "budget_change": None,
        }
    return {
        "detail": "The sample meets the minimum. No budget was changed.",
        "optimization": "proposal_only",
        "impressions": impressions,
        "budget_change": None,
    }


def attributed_outcomes(db: Session, tenant_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    if plan is None:
        return {"detail": "No operating plan is open.", "attributed_enquiries": 0, "opportunities": [], "impressions": None, "optimization": "insufficient_evidence"}
    marker = str(plan.id)
    leads = db.scalars(
        select(Lead).where(Lead.tenant_id == tenant_id, Lead.deleted_at.is_(None), Lead.utm_campaign == marker)
    ).all()
    opportunities = []
    if plan.campaign_id is not None:
        opportunities = db.scalars(
            select(Opportunity).where(
                Opportunity.tenant_id == tenant_id,
                Opportunity.deleted_at.is_(None),
                Opportunity.campaign_id == plan.campaign_id,
            )
        ).all()
    versions = db.scalars(
        select(CreativeVersion).where(CreativeVersion.tenant_id == tenant_id, CreativeVersion.plan_id == plan.id, CreativeVersion.deleted_at.is_(None))
    ).all()
    impressions = None
    for row in versions:
        if not row.metrics_json.strip():
            continue
        try:
            parsed = json.loads(row.metrics_json)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("impressions"), int):
            impressions = parsed["impressions"]
    optimization = "insufficient_evidence" if impressions is None or impressions < MINIMUM_IMPRESSIONS else "proposal_only"
    return {
        "detail": "Enquiries are counted from stored capture attribution. Missing provider metrics stay unavailable.",
        "attributed_enquiries": len(leads),
        "opportunities": [{"id": str(row.id), "name": row.name, "stage": row.stage} for row in opportunities],
        "impressions": impressions,
        "optimization": optimization,
        "budget_change": None,
    }


def resume_plan(db: Session, *, tenant_id: UUID, actor_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    if plan is None:
        return {"detail": "No operating plan is open.", "status": "blocked", "next_action": "start_operating_plan", "blocker": "", "plan_id": ""}
    if plan.blocker.startswith("Research limit"):
        return _detail(plan, plan.blocker)
    if plan.status == "blocked" and plan.blocker:
        plan.blocker = ""
    plan.status = "running"
    plan.next_action = plan.next_action if plan.next_action not in {"", "resolve_blocker"} else "research_prospects"
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="operating_plan.resume",
        entity_type="operating_plan",
        entity_id=str(plan.id),
        after={"status": plan.status},
    )
    return _detail(plan, "The operating plan is running.")


def marketing_board(db: Session, tenant_id: UUID) -> dict:
    plan = _latest_plan(db, tenant_id)
    products = _product_choices(db, tenant_id)
    if plan is None:
        return {
            "status": "absent",
            "next_action": "choose_product",
            "blocker": "Choose a product and its offer.",
            "versions": [],
            "products": products,
            "offer_name": "",
            "outcomes": {"attributed_enquiries": 0, "impressions": None, "optimization": "insufficient_evidence"},
        }
    reviewed = review_versions(db, tenant_id)
    outcomes = attributed_outcomes(db, tenant_id)
    snapshot = _load_snapshot(plan)
    return {
        "status": plan.status,
        "next_action": plan.next_action,
        "blocker": plan.blocker,
        "audience": plan.audience,
        "product_id": str(plan.product_id or ""),
        "offer_name": str(snapshot.get("name") or ""),
        "products": products,
        "research_runs": plan.research_runs,
        "research_limit": plan.research_limit,
        "versions": reviewed["versions"],
        "outcomes": {
            "attributed_enquiries": outcomes["attributed_enquiries"],
            "impressions": outcomes["impressions"],
            "optimization": outcomes["optimization"],
        },
    }
