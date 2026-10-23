from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import get_session
from app.models.assessment import AssessmentEvidence
from app.models.crm import Lead, Task
from app.models.execution import AuthorizationGrant
from app.models.integrations import EmailMessage
from app.models.operating_plan import CreativeVersion, OperatingPlan
from app.models.social import SocialPost
from app.providers.lead_discovery import DiscoveredLead, DiscoveryQuery, DiscoveryResult
from app.providers.social import MockSocialPublisher
from tests.conftest import login


class _Discovery:
    def health(self) -> dict:
        return {"provider": "fixture-discovery", "is_mock": True, "connected": False, "reason": "Fixture discovery."}

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        _ = query
        return DiscoveryResult(
            candidates=[
                DiscoveredLead(
                    first_name="Priya",
                    last_name="Nair",
                    email="priya.discovered@harbor-example.test",
                    title="Operations Lead",
                    company_name="Harbor Example",
                    linkedin_url="https://www.linkedin.com/in/priya-nair-example",
                    provider_ref="fixture-person-priya",
                    source_url="https://www.linkedin.com/in/priya-nair-example",
                )
            ],
            provider="fixture-discovery",
            is_mock=True,
            connected=False,
            reason="Fixture discovery returned one public profile.",
        )


def test_mock_mailbox_is_not_a_verified_live_mailbox(client: TestClient, mock_providers) -> None:
    _ = mock_providers
    headers = login(client)
    readiness = client.get("/api/v1/operating-plans/readiness", headers=headers, params={"channel": "email"})
    assert readiness.status_code == 200, readiness.text
    checks = {row["name"]: row for row in readiness.json()["data"]["checks"]}
    assert checks["mailbox"]["status"] == "fixture"
    assert checks["mailbox"]["status"] != "verified"
    assert "not a verified live mailbox" in checks["mailbox"]["reason"].lower()
    assert checks["live_demonstration"]["status"] == "blocked"
    assert readiness.json()["data"]["eligible_for_live_demo"] is False


def test_discovery_ranks_without_consent_and_collapses_duplicates(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: _Discovery())
    headers = login(client)
    grant = client.post(
        "/api/v1/workflow/grants",
        headers=headers,
        json={"name": "Discovery grant must not send", "mode": "bounded_autopilot", "workflow": "inbound", "channel": "email"},
    )
    assert grant.status_code == 200, grant.text
    try:
        _assert_discovered_prospect_is_not_emailed(client, headers)
    finally:
        db = get_session()
        try:
            rows = db.scalars(select(AuthorizationGrant).where(AuthorizationGrant.name == "Discovery grant must not send")).all()
            for row in rows:
                row.status = "revoked"
            db.commit()
        finally:
            db.close()


def _assert_discovered_prospect_is_not_emailed(client: TestClient, headers: dict) -> None:
    first = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert first.status_code == 200, first.text
    body = first.json()["data"]
    assert body["created"] == 1
    assert body["is_mock"] is True
    prospect = body["prospects"][0]
    assert prospect["response_eligible"] is False
    assert prospect["owner_name"]
    assert "consent" in prospect["next_action"].lower()
    assert "buying intent" in prospect["explanation"].lower()
    lead_id = prospect["lead_id"]
    db = get_session()
    try:
        lead = db.get(Lead, UUID(lead_id))
        assert lead is not None
        assert lead.consent_email is False
        assert lead.opt_out is False
        assert lead.provider_ref == "fixture-person-priya"
        evidence = db.scalars(select(AssessmentEvidence).where(AssessmentEvidence.tenant_id == lead.tenant_id)).all()
        assert any(row.source == "fixture-discovery" and "Operations Lead" in row.excerpt for row in evidence)
        task = db.scalar(select(Task).where(Task.entity_id == lead_id, Task.status == "open"))
        assert task is not None
        sent = db.scalar(select(func.count()).select_from(EmailMessage).where(EmailMessage.lead_id == lead.id))
        assert sent == 0
    finally:
        db.close()
    second = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert second.status_code == 200, second.text
    again = second.json()["data"]
    assert again["created"] == 0
    assert again["prospects"][0]["outcome"].startswith("duplicate")
    assert again["prospects"][0]["response_eligible"] is False


def test_operating_plan_publishes_only_an_authorized_version(client: TestClient, monkeypatch) -> None:
    calls: list[str] = []

    def publish_for_tenant(db, **kwargs):
        calls.append(str(kwargs["channel"]))
        row = SocialPost(
            tenant_id=kwargs.get("tenant_id"),
            created_by=kwargs.get("actor_id"),
            channel=kwargs["channel"],
            body=kwargs["body"],
            link_url=kwargs.get("link_url") or "",
            image_url=kwargs.get("image_url") or "",
            form_key_id=kwargs.get("form_key_id"),
            status="mock",
            provider="mock-linkedin",
            external_id="",
            permalink="",
            is_mock=True,
        )
        db.add(row)
        db.flush()
        return row

    monkeypatch.setattr("app.services.marketing.get_social_publisher", lambda channel: MockSocialPublisher(channel))
    monkeypatch.setattr("app.services.marketing.publish_post", publish_for_tenant)
    headers = login(client)
    created = client.post(
        "/api/v1/content/products",
        headers=headers,
        json={"sku": "plan-core", "name": "Core Platform", "description": "Core Platform helps operations teams run one revenue process."},
    )
    assert created.status_code == 200, created.text
    form = client.post("/api/v1/acquisition/form-keys", headers=headers, json={"name": "Plan capture"})
    assert form.status_code == 200, form.text
    product_id = created.json()["data"]["id"]
    db = get_session()
    try:
        open_plans = db.scalars(select(OperatingPlan).where(OperatingPlan.deleted_at.is_(None), OperatingPlan.status.in_(["running", "blocked", "paused"]))).all()
        for plan in open_plans:
            if str(plan.product_id) != product_id:
                plan.status = "completed"
        db.commit()
    finally:
        db.close()
    started = client.post(
        "/api/v1/operating-plans/start",
        headers=headers,
        params={"product_id": product_id},
    )
    assert started.status_code == 200, started.text
    assert started.json()["data"]["status"] == "running", started.text
    assert "Core Platform" in started.json()["data"]["detail"], started.text
    drafted = client.post("/api/v1/operating-plans/drafts", headers=headers)
    assert drafted.status_code == 200, drafted.text
    version_id = drafted.json()["data"]["version_id"]
    reviewed = client.get("/api/v1/operating-plans/review", headers=headers)
    version = next(row for row in reviewed.json()["data"]["versions"] if row["id"] == version_id)
    assert version["status"] == "draft"
    db = get_session()
    try:
        stored = db.get(CreativeVersion, UUID(version_id))
        assert stored is not None
        assert "Core Platform helps operations teams" in stored.body
        assert "impressions" not in stored.body.lower()
        original = stored.body
    finally:
        db.close()
    authorized = client.post("/api/v1/operating-plans/authorize", headers=headers, json={"version_id": version_id})
    assert authorized.status_code == 200, authorized.text
    revised = client.post(
        "/api/v1/operating-plans/revise",
        headers=headers,
        json={"version_id": version_id, "body": "A material edit that must be reviewed again."},
    )
    assert revised.status_code == 200, revised.text
    db = get_session()
    try:
        kept = db.get(CreativeVersion, UUID(version_id))
        assert kept is not None
        assert kept.body == original
        assert kept.status == "authorized"
    finally:
        db.close()
    scheduled = client.post("/api/v1/operating-plans/schedule", headers=headers, json={"version_id": version_id})
    assert scheduled.status_code == 200, scheduled.text
    published = client.post("/api/v1/operating-plans/publish", headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["detail"].endswith("unknown.") or "unknown" in published.json()["data"]["detail"]
    assert calls == ["linkedin"]
    db = get_session()
    try:
        version = db.get(CreativeVersion, UUID(version_id))
        assert version is not None and version.social_post_id is not None
        posted = db.get(SocialPost, version.social_post_id)
        assert posted is not None
        posted.external_id = "fixture-post-1"
        posted.status = "published"
        db.commit()
    finally:
        db.close()
    again = client.post("/api/v1/operating-plans/publish", headers=headers)
    assert again.status_code == 200, again.text
    assert "confirmed" in again.json()["data"]["detail"]
    assert calls == ["linkedin"]
    evidence = client.get("/api/v1/operating-plans/evidence", headers=headers)
    assert evidence.status_code == 200
    assert any(row["provider_ref"] == "fixture-post-1" for row in evidence.json()["data"]["evidence"])
    outcomes = client.get("/api/v1/operating-plans/outcomes", headers=headers)
    assert outcomes.json()["data"]["impressions"] is None
    assert outcomes.json()["data"]["optimization"] == "insufficient_evidence"
    assert outcomes.json()["data"]["budget_change"] is None
    measured = client.post("/api/v1/operating-plans/metrics", headers=headers, json={"version_id": version_id, "impressions": 12})
    assert measured.json()["data"]["optimization"] == "insufficient_evidence"
    assert measured.json()["data"]["budget_change"] is None


def test_instagram_localhost_and_live_form_do_not_reach_the_publisher(client: TestClient, monkeypatch) -> None:
    calls: list[str] = []

    class _Live:
        pass

    def publish(db, **kwargs):
        _ = db
        calls.append(kwargs["channel"])
        raise AssertionError("publisher was called")

    monkeypatch.setattr("app.services.marketing.get_social_publisher", lambda channel: _Live())
    monkeypatch.setattr("app.services.marketing.publish_post", publish)
    headers = login(client)
    created = client.post(
        "/api/v1/content/products",
        headers=headers,
        json={"sku": "plan-ig", "name": "Instagram Offer", "description": "Instagram Offer explains the product without a metric."},
    )
    client.post("/api/v1/acquisition/form-keys", headers=headers, json={"name": "Instagram capture"})
    product_id = created.json()["data"]["id"]
    db = get_session()
    try:
        open_plans = db.scalars(select(OperatingPlan).where(OperatingPlan.deleted_at.is_(None), OperatingPlan.status.in_(["running", "blocked", "paused"]))).all()
        for plan in open_plans:
            if str(plan.product_id) != product_id:
                plan.status = "completed"
        db.commit()
    finally:
        db.close()
    started = client.post(
        "/api/v1/operating-plans/start",
        headers=headers,
        params={"channel": "instagram", "product_id": product_id},
    )
    assert started.status_code == 200, started.text
    db = get_session()
    try:
        plan = db.scalar(select(OperatingPlan).order_by(OperatingPlan.created_at.desc()))
        assert plan is not None
        plan.channel = "instagram"
        db.commit()
    finally:
        db.close()
    drafted = client.post("/api/v1/operating-plans/drafts", headers=headers)
    version_id = drafted.json()["data"]["version_id"]
    client.post("/api/v1/operating-plans/authorize", headers=headers, json={"version_id": version_id})
    client.post("/api/v1/operating-plans/schedule", headers=headers, json={"version_id": version_id})
    db = get_session()
    try:
        others = db.scalars(select(CreativeVersion).where(CreativeVersion.id != UUID(version_id), CreativeVersion.status == "scheduled")).all()
        for row in others:
            row.status = "authorized"
        db.commit()
    finally:
        db.close()
    published = client.post("/api/v1/operating-plans/publish", headers=headers)
    assert published.status_code == 200, published.text
    assert "cannot fetch" in published.json()["data"]["detail"].lower()
    assert calls == []
