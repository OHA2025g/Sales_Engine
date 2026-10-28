"""Product-aware organic acquisition without a live post or a live send."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import get_session
from app.models.ai import AIApproval
from app.models.assessment import AssessmentDecision
from app.models.autonomy import AutonomousRun, AutonomousRunStep, AutopilotSettings
from app.models.content import SellerProfile
from app.models.crm import Lead, Opportunity
from app.models.identity import DomainEvent, Tenant, User
from app.models.integrations import EmailMessage
from app.models.lifecycle import Product
from app.models.operating_plan import CreativeVersion, DemoScope, OperatingPlan
from app.models.social import SocialPost
from app.providers.lead_discovery import DiscoveryResult
from app.providers.social import LinkedInSocialPublisher, MetaSocialPublisher, MockSocialPublisher
from app.services.autonomy import run_autonomous_cycle
from app.services.demo_guard import (
    DEMO_DISCOVERY_BLOCK,
    DISCOVERY_OUTSIDE,
    PREPARED_BLOCK,
    external_execution_block,
    seal_scope,
)
from app.services.discovery import run_discovery
from app.services.effects import EffectAttempt, ReconciledEffect, execute_external_effect
from app.services.marketing import authorize_version, generate_draft, schedule_version
from app.services.public_forms import create_form_key
from app.workers.celery_app import process_outbox, publish_due_operating_plans
from tests.conftest import login

OFFER = "Autonomous Revenue OS"


class BillableDiscovery:
    def __init__(self) -> None:
        self.calls = 0

    def health(self) -> dict:
        return {"provider": "apify", "is_mock": False, "connected": True, "reason": "stub"}

    def discover(self, query) -> DiscoveryResult:
        self.calls += 1
        _ = query
        return DiscoveryResult(candidates=[], provider="apify", is_mock=False, connected=True)


def _user(db, email: str = "admin@agrayian.demo") -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def _close_scopes(db, tenant_id) -> None:
    rows = db.scalars(
        select(DemoScope).where(
            DemoScope.tenant_id == tenant_id,
            DemoScope.deleted_at.is_(None),
            DemoScope.status.in_(["prepared", "authorized"]),
        )
    ).all()
    for row in rows:
        row.status = "closed"


def _close_plans(db, tenant_id) -> None:
    rows = db.scalars(
        select(OperatingPlan).where(
            OperatingPlan.tenant_id == tenant_id,
            OperatingPlan.deleted_at.is_(None),
            OperatingPlan.status.in_(["running", "blocked", "paused"]),
        )
    ).all()
    for row in rows:
        row.status = "completed"


def _fake_social(monkeypatch) -> None:
    def _mock(channel: str) -> MockSocialPublisher:
        return MockSocialPublisher(channel or "linkedin")

    def _refuse(self, **kwargs) -> None:
        _ = (self, kwargs)
        raise AssertionError("A live social publisher was called")

    monkeypatch.setattr("app.services.marketing.get_social_publisher", _mock)
    monkeypatch.setattr("app.services.social.get_social_publisher", _mock)
    monkeypatch.setattr("app.providers.social.get_social_publisher", _mock)
    monkeypatch.setattr(LinkedInSocialPublisher, "publish", _refuse)
    monkeypatch.setattr(MetaSocialPublisher, "publish", _refuse)
    settings = get_settings()
    monkeypatch.setattr(settings, "linkedin_posting_mode", "mock")
    monkeypatch.setattr(settings, "meta_posting_mode", "mock")
    monkeypatch.setattr(settings, "email_provider", "mock")


def test_second_demo_tenant_cannot_run_billable_discovery(client: TestClient, monkeypatch) -> None:
    _ = client
    stub = BillableDiscovery()
    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: stub)
    db = get_session()
    settings = None
    saved: dict = {}
    try:
        user = _user(db, "admin@northline.demo")
        _close_scopes(db, user.tenant_id)
        settings = db.scalar(select(AutopilotSettings).where(AutopilotSettings.tenant_id == user.tenant_id))
        assert settings is not None
        saved = {
            "enabled": settings.enabled,
            "discovery_enabled": settings.discovery_enabled,
            "market_monitoring_enabled": settings.market_monitoring_enabled,
            "campaign_planning_enabled": settings.campaign_planning_enabled,
            "deal_monitoring_enabled": settings.deal_monitoring_enabled,
            "proposal_preparation_enabled": settings.proposal_preparation_enabled,
            "max_leads_per_day": settings.max_leads_per_day,
            "quiet_hours_start": settings.quiet_hours_start,
            "quiet_hours_end": settings.quiet_hours_end,
        }
        settings.enabled = True
        settings.discovery_enabled = True
        settings.market_monitoring_enabled = False
        settings.campaign_planning_enabled = False
        settings.deal_monitoring_enabled = False
        settings.proposal_preparation_enabled = False
        settings.max_leads_per_day = 0
        settings.quiet_hours_start = "00:00"
        settings.quiet_hours_end = "00:00"
        db.commit()
        blocked = run_discovery(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            search_query="revenue leaders",
            provider=stub,
            enforce_budget=False,
        )
        assert blocked["execution_blocked"] is True
        assert blocked["reason"] == DEMO_DISCOVERY_BLOCK
        assert stub.calls == 0
        monkeypatch.setattr("app.services.autonomy.process_pending_events", lambda *args, **kwargs: 0)
        monkeypatch.setattr("app.services.autonomy.due_sequence_work", lambda *args, **kwargs: {})
        monkeypatch.setattr("app.services.autonomy.queue_voice_dial", lambda *args, **kwargs: None)
        run = run_autonomous_cycle(db, tenant_id=user.tenant_id, actor_id=user.id, trigger="schedule")
        step = db.scalar(select(AutonomousRunStep).where(AutonomousRunStep.run_id == run.id, AutonomousRunStep.name == "discover"))
        assert step is not None
        assert DEMO_DISCOVERY_BLOCK in (step.detail_json or "")
        assert stub.calls == 0
    finally:
        if settings is not None and saved:
            for name, value in saved.items():
                setattr(settings, name, value)
            db.commit()
        db.close()


def test_prepared_scope_cannot_execute_external_effects(client: TestClient, monkeypatch) -> None:
    _ = client
    _fake_social(monkeypatch)
    stub = BillableDiscovery()
    db = get_session()
    scope = None
    try:
        user = _user(db, "admin@northline.demo")
        tenant_id = user.tenant_id
        _close_scopes(db, tenant_id)
        _close_plans(db, tenant_id)
        product = Product(
            tenant_id=user.tenant_id,
            created_by=user.id,
            sku="GOV",
            name="One-time setup, under 200 employees",
            kind="one_time",
            list_price=Decimal("300000"),
            currency="INR",
            description="One-time setup for a company under 200 employees.",
        )
        db.add(product)
        db.flush()
        plan = OperatingPlan(
            tenant_id=user.tenant_id,
            created_by=user.id,
            product_id=product.id,
            channel="linkedin",
            audience="Founders in India",
            status="running",
            next_action="generate_draft",
            context_snapshot=json.dumps(
                {
                    "name": OFFER,
                    "customer_facing_name": OFFER,
                    "description": "One workspace runs the revenue cycle.",
                    "customer_audience": "Founders in India",
                    "kind": "one_time",
                    "list_price": "300000",
                    "currency": "INR",
                    "sku": "GOV",
                }
            ),
        )
        db.add(plan)
        db.flush()
        create_form_key(db, tenant_id=user.tenant_id, actor_id=user.id, name="prepared-organic")
        drafted = generate_draft(db, tenant_id=user.tenant_id, actor_id=user.id)
        version = db.get(CreativeVersion, UUID(drafted["version_id"]))
        assert version is not None
        authorize_version(db, tenant_id=user.tenant_id, actor_id=user.id, version_id=version.id)
        schedule_version(db, tenant_id=user.tenant_id, actor_id=user.id, version_id=version.id)
        version.scheduled_for = datetime.now(UTC) - timedelta(minutes=1)
        scope = DemoScope(
            tenant_id=user.tenant_id,
            created_by=user.id,
            plan_id=plan.id,
            version_id=version.id,
            channel="linkedin",
            status="prepared",
            expires_at=datetime.now(UTC) + timedelta(days=2),
            allowed_actions=json.dumps({"social.publish": 1, "email.acknowledge": 1}),
        )
        db.add(scope)
        db.commit()
        scope_id = scope.id
        version_id = version.id
        assert external_execution_block(db, tenant_id=user.tenant_id, action="social.publish", target_id=str(version.id), channel="linkedin") == PREPARED_BLOCK
        assert external_execution_block(db, tenant_id=user.tenant_id, action="email.acknowledge", recipient="buyer@example.com") == PREPARED_BLOCK
        blocked = run_discovery(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            search_query="revenue leaders",
            provider=stub,
            enforce_budget=False,
        )
        assert blocked["reason"] == PREPARED_BLOCK
        assert stub.calls == 0
        db.commit()
        db.close()
        publish_due_operating_plans()
        db = get_session()
        scope = db.get(DemoScope, scope_id)
        version = db.get(CreativeVersion, version_id)
        assert scope is not None and scope.status == "prepared"
        assert version is not None and version.status == "scheduled"
        assert version.social_post_id is None
        posts = db.scalars(select(SocialPost).where(SocialPost.tenant_id == tenant_id, SocialPost.link_url.contains(version.publication_token))).all()
        assert list(posts) == []
    finally:
        if scope is not None:
            current = db.get(DemoScope, scope.id)
            if current is not None:
                current.status = "closed"
            held = db.scalars(
                select(CreativeVersion).where(
                    CreativeVersion.tenant_id == scope.tenant_id,
                    CreativeVersion.status == "scheduled",
                    CreativeVersion.deleted_at.is_(None),
                )
            ).all()
            for row in held:
                row.status = "authorized"
                row.scheduled_for = None
            db.commit()
        db.close()


def test_authorized_discovery_scope_is_explicit_and_pilot_is_unchanged(client: TestClient) -> None:
    _ = client
    db = get_session()
    tenant = None
    scope = None
    try:
        user = _user(db, "admin@northline.demo")
        tenant = db.get(Tenant, user.tenant_id)
        assert tenant is not None
        _close_scopes(db, user.tenant_id)
        stub = BillableDiscovery()
        scope = DemoScope(
            tenant_id=user.tenant_id,
            created_by=user.id,
            status="authorized",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            allowed_actions=json.dumps({"email.acknowledge": 1}),
        )
        db.add(scope)
        db.flush()
        seal_scope(scope)
        db.commit()
        outside = run_discovery(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            search_query="revenue leaders",
            provider=stub,
            enforce_budget=False,
        )
        assert outside["reason"] == DISCOVERY_OUTSIDE
        assert stub.calls == 0
        scope.allowed_actions = json.dumps({"discovery.search": 1})
        seal_scope(scope)
        db.commit()
        allowed = run_discovery(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            search_query="revenue leaders",
            provider=stub,
            enforce_budget=False,
        )
        assert stub.calls == 1
        assert allowed.get("execution_blocked") is not True
        scope.status = "closed"
        tenant.operating_mode = "PILOT"
        db.commit()
        pilot = BillableDiscovery()
        run_discovery(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            search_query="revenue leaders",
            provider=pilot,
            enforce_budget=False,
        )
        assert pilot.calls == 1
    finally:
        if tenant is not None:
            tenant.operating_mode = "DEMO"
        if scope is not None:
            current = db.get(DemoScope, scope.id)
            if current is not None:
                current.status = "closed"
        db.commit()
        db.close()


def test_due_schedule_attributes_one_mock_publication_and_prepares_one_reply(client: TestClient, monkeypatch) -> None:
    _fake_social(monkeypatch)
    headers = login(client)
    db = get_session()
    try:
        user = _user(db)
        _close_scopes(db, user.tenant_id)
        _close_plans(db, user.tenant_id)
        profile = db.scalar(select(SellerProfile).where(SellerProfile.tenant_id == user.tenant_id, SellerProfile.deleted_at.is_(None)))
        if profile is None:
            profile = SellerProfile(tenant_id=user.tenant_id, created_by=user.id)
            db.add(profile)
        profile.company_name = "AGRAYIAN AI Labs"
        profile.summary = "AGRAYIAN AI Labs sells the Autonomous Revenue OS. One workspace runs the revenue cycle."
        profile.proof = "The workspace itself is the product."
        gov = Product(
            tenant_id=user.tenant_id,
            created_by=user.id,
            sku="GOV",
            name="One-time setup, under 200 employees",
            kind="one_time",
            list_price=Decimal("300000"),
            currency="INR",
            description="One-time setup for a company under 200 employees.",
        )
        core = Product(
            tenant_id=user.tenant_id,
            created_by=user.id,
            sku="CORE-LEAK",
            name="Revenue OS monthly",
            kind="subscription",
            list_price=Decimal("50000"),
            currency="INR",
            description="Starting monthly price of 50000 for 50 to 200 employees.",
        )
        larger = Product(
            tenant_id=user.tenant_id,
            created_by=user.id,
            sku="CS-LEAK",
            name="One-time setup, 200 to 1,000 employees",
            kind="one_time",
            list_price=Decimal("400000"),
            currency="INR",
            description="One-time setup for a company of 200 to 1,000 employees.",
        )
        db.add_all([gov, core, larger])
        db.flush()
        plan = OperatingPlan(
            tenant_id=user.tenant_id,
            created_by=user.id,
            product_id=gov.id,
            channel="linkedin",
            audience="India B2B revenue teams · technology,software · india · CEO",
            status="running",
            next_action="generate_draft",
            context_snapshot=json.dumps(
                {
                    "name": OFFER,
                    "customer_facing_name": OFFER,
                    "sku": "GOV",
                    "catalogue_name": "One-time setup, under 200 employees",
                    "description": "One workspace runs the revenue cycle. Autopilot prepares the work. A person approves send, spend, and dial.",
                    "customer_audience": "Founders, CEOs, CROs, and revenue leaders at B2B companies in India with a sales team",
                    "kind": "one_time",
                    "list_price": "300000",
                    "currency": "INR",
                    "offer_lines": [
                        {"description": "One-time setup of ₹3,00,000 for a company under 200 employees."},
                        {"description": "Starting monthly price of ₹50,000 for a company of about 50 to 200 employees."},
                    ],
                }
            ),
        )
        db.add(plan)
        db.flush()
        create_form_key(db, tenant_id=user.tenant_id, actor_id=user.id, name="organic-journey")
        drafted = generate_draft(db, tenant_id=user.tenant_id, actor_id=user.id)
        db.commit()
        version = db.get(CreativeVersion, UUID(drafted["version_id"]))
        assert version is not None
        assert version.headline == OFFER
        assert "GOV" not in version.headline
        assert "GOV" not in version.body
        visible = version.body.replace(version.publication_token, "")
        assert "INR 300,000" in visible
        assert "under 200 employees" in visible
        assert "50,000" not in visible
        assert "50000" not in visible
        assert "400,000" not in visible
        assert "400000" not in visible
        assert "200 to 1,000" not in visible
        assert "Revenue OS monthly" not in version.body
        assert "Governance Pack" not in version.body
        assert version.publication_token in version.body
        stored = json.loads(version.context_json)
        assert stored["customer_facing_name"] == OFFER
        assert stored["sku"] == "GOV"
        assert stored["price_amount"] == "300,000"
        authorize_version(db, tenant_id=user.tenant_id, actor_id=user.id, version_id=version.id)
        schedule_version(db, tenant_id=user.tenant_id, actor_id=user.id, version_id=version.id)
        version.scheduled_for = datetime.now(UTC) + timedelta(days=2)
        token = version.publication_token
        plan_id = plan.id
        product_id = gov.id
        tenant_id = user.tenant_id
        opportunities_before = int(
            db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.tenant_id == tenant_id, Opportunity.deleted_at.is_(None))) or 0
        )
        db.commit()
    finally:
        db.close()

    publish_due_operating_plans()
    db = get_session()
    try:
        version = db.scalar(select(CreativeVersion).where(CreativeVersion.publication_token == token))
        assert version is not None and version.status == "scheduled"
        assert version.social_post_id is None
        version.scheduled_for = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
    finally:
        db.close()

    publish_due_operating_plans()
    publish_due_operating_plans()
    db = get_session()
    try:
        version = db.scalar(select(CreativeVersion).where(CreativeVersion.publication_token == token))
        assert version is not None
        assert version.status == "published"
        assert version.outcome == "mock"
        assert version.provider_ref == ""
        post = db.get(SocialPost, version.social_post_id)
        assert post is not None
        assert post.is_mock is True
        assert post.external_id == ""
        assert post.status == "mock"
        assert token in post.link_url
        posts = db.scalars(select(SocialPost).where(SocialPost.tenant_id == tenant_id, SocialPost.link_url.contains(token))).all()
        assert len(list(posts)) == 1
    finally:
        db.close()

    email = f"organic.{uuid4().hex[:8]}@example.com"
    payload = {
        "first_name": "Asha",
        "last_name": "Rao",
        "email": email,
        "consent_email": True,
        "source": "public_form",
        "request_note": "We want to see how the workspace runs.",
        "publication": token,
        "utm_campaign": "not-a-real-plan",
    }
    first = client.post("/api/v1/acquisition/capture", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    process_outbox()
    process_outbox()
    second = client.post("/api/v1/acquisition/capture", headers=headers, json=payload)
    assert second.status_code == 200, second.text
    process_outbox()

    price_email = f"price.{uuid4().hex[:8]}@example.com"
    priced = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={
            "first_name": "Asha",
            "last_name": "Rao",
            "email": price_email,
            "consent_email": True,
            "source": "public_form",
            "request_note": "What is the setup price?",
            "publication": token,
        },
    )
    assert priced.status_code == 200, priced.text
    process_outbox()
    process_outbox()

    other_headers = login(client, "admin@northline.demo")
    foreign = client.post(
        "/api/v1/acquisition/capture",
        headers=other_headers,
        json={
            "first_name": "Other",
            "last_name": "Tenant",
            "email": f"foreign.{uuid4().hex[:8]}@example.com",
            "company_name": "Elsewhere",
            "consent_email": True,
            "source": "public_form",
            "request_note": "What is the setup price?",
            "publication": token,
            "utm_campaign": str(plan_id),
        },
    )
    assert foreign.status_code == 200, foreign.text

    db = get_session()
    try:
        leads = db.scalars(select(Lead).where(Lead.tenant_id == tenant_id, Lead.email == email, Lead.deleted_at.is_(None))).all()
        assert len(list(leads)) == 1
        lead = leads[0]
        assert lead.creative_version_id is not None
        assert lead.operating_plan_id == plan_id
        assert lead.social_post_id is not None
        assert lead.utm_campaign == str(plan_id)
        assert lead.title == ""
        decision = db.scalar(select(AssessmentDecision).where(AssessmentDecision.lead_id == lead.id, AssessmentDecision.deleted_at.is_(None)))
        assert decision is not None
        assert decision.response_eligible is True
        assert decision.sales_qualified is False
        qualified = db.scalar(
            select(DomainEvent).where(
                DomainEvent.tenant_id == tenant_id,
                DomainEvent.event_type == "lead.sales_qualified",
                DomainEvent.entity_id == str(lead.id),
            )
        )
        assert qualified is None
        opportunities_after = int(
            db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.tenant_id == tenant_id, Opportunity.deleted_at.is_(None))) or 0
        )
        assert opportunities_after == opportunities_before
        approvals = db.scalars(
            select(AIApproval).where(
                AIApproval.tenant_id == tenant_id,
                AIApproval.entity_id == str(lead.id),
                AIApproval.action_type == "email.acknowledge",
                AIApproval.deleted_at.is_(None),
            )
        ).all()
        assert len(list(approvals)) == 1
        approval = approvals[0]
        assert approval.status == "pending"
        body = json.loads(approval.payload_json)["body"]
        assert OFFER in body
        assert "AGRAYIAN AI Labs" in body
        assert "We want to see how the workspace runs." in body
        assert "300,000" not in body
        assert "50,000" not in body
        assert "400,000" not in body
        assert "GOV" not in body
        assert "What industry is the company in?" in body
        assert "About how many people work there?" in body
        assert "What is your role?" in body
        assert "What should we help with?" not in body
        messages = db.scalars(select(EmailMessage).where(EmailMessage.lead_id == lead.id, EmailMessage.direction == "outbound")).all()
        assert list(messages) == []
        version = db.get(CreativeVersion, lead.creative_version_id)
        assert version is not None and version.plan_id == plan_id
        frozen = json.loads(version.context_json)
        assert frozen["sources"]["product_id"] == str(product_id)
        priced_lead = db.scalar(select(Lead).where(Lead.tenant_id == tenant_id, Lead.email == price_email))
        assert priced_lead is not None and priced_lead.creative_version_id == lead.creative_version_id
        priced_approval = db.scalar(
            select(AIApproval).where(AIApproval.tenant_id == tenant_id, AIApproval.entity_id == str(priced_lead.id), AIApproval.action_type == "email.acknowledge")
        )
        assert priced_approval is not None
        priced_body = json.loads(priced_approval.payload_json)["body"]
        assert "INR 300,000" in priced_body
        assert "under 200 employees" in priced_body
        assert "50,000" not in priced_body
        assert "400,000" not in priced_body
        assert "GOV" not in priced_body
        foreign_lead = db.scalar(select(Lead).where(Lead.email == foreign.json()["data"]["lead"]["email"]))
        assert foreign_lead is not None
        assert foreign_lead.creative_version_id is None
        assert foreign_lead.operating_plan_id is None
        assert foreign_lead.tenant_id != tenant_id
    finally:
        db.close()


def test_provider_reconciliation_still_confirms_without_a_second_call(client: TestClient) -> None:
    _ = client
    db = get_session()
    try:
        user = _user(db)
        calls = {"count": 0}

        def call() -> EffectAttempt:
            calls["count"] += 1
            return EffectAttempt()

        def reconcile(effect) -> ReconciledEffect:
            _ = effect
            return ReconciledEffect("confirmed", "urn:li:share:42")

        run = AutonomousRun(
            tenant_id=user.tenant_id,
            created_by=user.id,
            status="running",
            trigger="manual",
            workflow="marketing",
            trigger_event="reconcile-check",
            summary="Reconcile",
        )
        db.add(run)
        db.flush()
        first = execute_external_effect(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            run=run,
            action="social.publish",
            channel="linkedin",
            target_id=str(uuid4()),
            content_version="hash-one",
            grant_id="",
            call=call,
            reconcile=reconcile,
        )
        assert first.outcome == "unknown"
        assert calls["count"] == 1
        second = execute_external_effect(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            run=run,
            action="social.publish",
            channel="linkedin",
            target_id=first.target_id,
            content_version="hash-one",
            grant_id="",
            call=call,
            reconcile=reconcile,
        )
        assert calls["count"] == 1
        assert second.outcome == "confirmed"
        assert second.provider_ref == "urn:li:share:42"
    finally:
        db.rollback()
        db.close()
