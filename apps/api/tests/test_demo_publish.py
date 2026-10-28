"""A DEMO tenant cannot publish for real without an authorized scope."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_session
from app.models.identity import Tenant, User
from app.models.operating_plan import CreativeVersion, DemoScope, OperatingPlan
from app.providers.social import LinkedInSocialPublisher, MetaSocialPublisher, SocialPublishResult
from app.services.demo_guard import DEMO_PUBLISH_BLOCK, PREPARED_BLOCK, seal_scope
from app.services.marketing import publish_scheduled
from app.services.public_forms import create_form_key
from app.services.social import publish_post
from tests.conftest import login


class LiveStub(LinkedInSocialPublisher):
    def __init__(self) -> None:
        self.calls = 0

    def publish(self, **kwargs) -> SocialPublishResult:
        self.calls += 1
        _ = kwargs
        return SocialPublishResult(ok=True, provider="linkedin", is_mock=False, external_id="stub-post", permalink="")


def _user(db) -> User:
    user = db.scalar(select(User).where(User.email == "admin@agrayian.demo"))
    assert user is not None
    return user


def _hash(headline: str, body: str) -> str:
    return hashlib.sha256(f"{headline}|{body}|".encode()).hexdigest()


def _refuse(self, **kwargs) -> None:
    _ = (self, kwargs)
    raise AssertionError("A live social publisher was called")


def _patch_live(monkeypatch, stub: LiveStub) -> None:
    monkeypatch.setattr("app.services.marketing.get_social_publisher", lambda channel: stub)
    monkeypatch.setattr("app.services.social.get_social_publisher", lambda channel: stub)
    monkeypatch.setattr("app.providers.social.get_social_publisher", lambda channel: stub)
    monkeypatch.setattr(LinkedInSocialPublisher, "publish", _refuse)
    monkeypatch.setattr(MetaSocialPublisher, "publish", _refuse)
    monkeypatch.setattr("app.services.marketing._public_url", lambda url: True)
    settings = get_settings()
    monkeypatch.setattr(settings, "linkedin_posting_mode", "mock")
    monkeypatch.setattr(settings, "meta_posting_mode", "mock")


def _close_open(db, tenant_id) -> list[tuple]:
    scopes = db.scalars(
        select(DemoScope).where(
            DemoScope.tenant_id == tenant_id,
            DemoScope.deleted_at.is_(None),
            DemoScope.status.in_(["prepared", "authorized"]),
        )
    ).all()
    plans = db.scalars(
        select(OperatingPlan).where(
            OperatingPlan.tenant_id == tenant_id,
            OperatingPlan.deleted_at.is_(None),
            OperatingPlan.status.in_(["running", "blocked", "paused"]),
        )
    ).all()
    saved = ([(row.id, row.status) for row in scopes], [(row.id, row.status) for row in plans])
    for row in scopes:
        row.status = "closed"
    for row in plans:
        row.status = "completed"
    return saved


def _scheduled_version(db, user: User) -> CreativeVersion:
    plan = OperatingPlan(
        tenant_id=user.tenant_id,
        created_by=user.id,
        channel="linkedin",
        audience="Fixture",
        status="running",
        next_action="publish_scheduled",
    )
    db.add(plan)
    db.flush()
    headline = "Fixture headline"
    body = "Fixture body"
    version = CreativeVersion(
        tenant_id=user.tenant_id,
        created_by=user.id,
        plan_id=plan.id,
        channel="linkedin",
        version_number=1,
        headline=headline,
        body=body,
        content_hash=_hash(headline, body),
        status="scheduled",
        scheduled_for=datetime.now(UTC) - timedelta(minutes=1),
    )
    db.add(version)
    db.flush()
    return version


def _scope(db, user: User, version: CreativeVersion, *, status: str, allowed: dict, expires: datetime | None) -> DemoScope:
    scope = DemoScope(
        tenant_id=user.tenant_id,
        created_by=user.id,
        version_id=version.id,
        plan_id=version.plan_id,
        channel="linkedin",
        status=status,
        expires_at=expires,
        content_hash=version.content_hash,
        allowed_actions=json.dumps(allowed),
        action_limit=1,
    )
    db.add(scope)
    db.flush()
    if status == "authorized":
        seal_scope(scope)
    return scope


def test_missing_prepared_expired_wrong_and_authorized_scopes(client: TestClient, monkeypatch) -> None:
    _ = client
    login(client)
    stub = LiveStub()
    _patch_live(monkeypatch, stub)
    db = get_session()
    try:
        user = _user(db)
        _close_open(db, user.tenant_id)
        version = _scheduled_version(db, user)
        create_form_key(db, tenant_id=user.tenant_id, actor_id=user.id, name=f"publish-{version.id.hex[:8]}")

        direct = publish_post(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            channel="linkedin",
            body="Direct fixture",
            scope_target_id=str(version.id),
        )
        scheduled = publish_scheduled(db, tenant_id=user.tenant_id, actor_id=user.id)
        assert direct.error == DEMO_PUBLISH_BLOCK
        assert scheduled["blocker"] == DEMO_PUBLISH_BLOCK
        assert stub.calls == 0

        prepared = _scope(db, user, version, status="prepared", allowed={"social.publish": 1}, expires=datetime.now(UTC) + timedelta(days=1))
        direct = publish_post(
            db, tenant_id=user.tenant_id, actor_id=user.id, channel="linkedin", body="Prepared", scope_target_id=str(version.id)
        )
        scheduled = publish_scheduled(db, tenant_id=user.tenant_id, actor_id=user.id)
        assert direct.error == PREPARED_BLOCK
        assert scheduled["blocker"] == PREPARED_BLOCK
        assert prepared.status == "prepared"
        assert stub.calls == 0
        prepared.deleted_at = datetime.now(UTC)

        expired = _scope(
            db,
            user,
            version,
            status="authorized",
            allowed={"social.publish": 1},
            expires=datetime.now(UTC) - timedelta(minutes=5),
        )
        direct = publish_post(
            db, tenant_id=user.tenant_id, actor_id=user.id, channel="linkedin", body="Expired", scope_target_id=str(version.id)
        )
        scheduled = publish_scheduled(db, tenant_id=user.tenant_id, actor_id=user.id)
        assert "expired" in direct.error
        assert "expired" in scheduled["blocker"]
        assert stub.calls == 0
        expired.deleted_at = datetime.now(UTC)

        wrong = _scope(
            db,
            user,
            version,
            status="authorized",
            allowed={"email.send": 1},
            expires=datetime.now(UTC) + timedelta(days=1),
        )
        direct = publish_post(
            db, tenant_id=user.tenant_id, actor_id=user.id, channel="linkedin", body="Wrong action", scope_target_id=str(version.id)
        )
        scheduled = publish_scheduled(db, tenant_id=user.tenant_id, actor_id=user.id)
        assert direct.error == "That action is outside the controlled demonstration."
        assert scheduled["blocker"] == "That action is outside the controlled demonstration."
        assert stub.calls == 0
        wrong.deleted_at = datetime.now(UTC)

        _scope(
            db,
            user,
            version,
            status="authorized",
            allowed={"social.publish": 1},
            expires=datetime.now(UTC) + timedelta(days=1),
        )
        direct = publish_post(
            db, tenant_id=user.tenant_id, actor_id=user.id, channel="linkedin", body="Authorized", scope_target_id=str(version.id)
        )
        assert direct.status == "published"
        assert stub.calls == 1
        scheduled = publish_scheduled(db, tenant_id=user.tenant_id, actor_id=user.id)
        assert stub.calls == 2
        assert scheduled["blocker"] == ""
    finally:
        db.rollback()
        db.close()


def test_mock_publish_stays_available_and_pilot_is_not_blocked(client: TestClient, monkeypatch) -> None:
    _ = client
    login(client)
    stub = LiveStub()
    db = get_session()
    try:
        user = _user(db)
        tenant = db.get(Tenant, user.tenant_id)
        assert tenant is not None
        _close_open(db, user.tenant_id)
        settings = get_settings()
        monkeypatch.setattr(settings, "linkedin_posting_mode", "mock")
        monkeypatch.setattr(LinkedInSocialPublisher, "publish", _refuse)
        monkeypatch.setattr(MetaSocialPublisher, "publish", _refuse)
        posted = publish_post(db, tenant_id=user.tenant_id, actor_id=user.id, channel="linkedin", body="Mock stays available")
        assert posted.status == "mock"
        assert posted.is_mock is True

        tenant.operating_mode = "PILOT"
        version = _scheduled_version(db, user)
        create_form_key(db, tenant_id=user.tenant_id, actor_id=user.id, name=f"pilot-{version.id.hex[:8]}")
        _patch_live(monkeypatch, stub)
        scheduled = publish_scheduled(db, tenant_id=user.tenant_id, actor_id=user.id)
        assert scheduled["blocker"] != DEMO_PUBLISH_BLOCK
        assert stub.calls == 1
    finally:
        db.rollback()
        db.close()
