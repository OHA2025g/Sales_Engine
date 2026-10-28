"""Stale-work holds, mail-loop limits, explicit offers, and demonstration scope."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import get_session
from app.models.ai import AIApproval
from app.models.autonomy import AutopilotSettings
from app.models.crm import Lead
from app.models.execution import AuthorizationGrant
from app.models.identity import AuditLog, DomainEvent, User
from app.models.integrations import EmailMessage
from app.models.lifecycle import Conversation, Product
from app.models.operating_plan import CreativeVersion, DemoScope, OperatingPlan
from app.services.demo_guard import external_execution_block, seal_scope
from app.services.email_send import execute_email_send, retry_retrying_sends
from app.services.event_delivery import replay_event
from app.services.external_hold import hold_stale_external_work
from app.services.grants import send_authorization
from app.services.marketing import generate_draft
from app.services.reply_router import route_reply
from app.workers.celery_app import process_outbox
from app.workers.health import worker_heartbeat_fresh
from tests.conftest import login


def _user(db) -> User:
    user = db.scalar(select(User).where(User.email == "admin@agrayian.demo"))
    assert user is not None
    return user


def test_stale_external_work_is_held_and_kept(client: TestClient) -> None:
    _ = client
    db = get_session()
    try:
        user = _user(db)
        now = datetime.now(UTC)
        old_event = DomainEvent(
            tenant_id=user.tenant_id,
            event_type="lead.created",
            entity_type="lead",
            entity_id=str(uuid4()),
            delivery_status="pending",
            created_at=now - timedelta(days=30),
        )
        fresh_event = DomainEvent(
            tenant_id=user.tenant_id,
            event_type="lead.scored",
            entity_type="lead",
            entity_id=str(uuid4()),
            delivery_status="pending",
        )
        expired = AIApproval(
            tenant_id=user.tenant_id,
            created_by=user.id,
            action_level=2,
            action_type="email.send",
            title="Old send",
            payload_json="{}",
            status="pending",
            expires_at=now - timedelta(days=1),
        )
        current = AIApproval(
            tenant_id=user.tenant_id,
            created_by=user.id,
            action_level=2,
            action_type="email.send",
            title="Current send",
            payload_json="{}",
            status="pending",
            expires_at=now + timedelta(days=7),
        )
        db.add_all([old_event, fresh_event, expired, current])
        db.commit()
        counts = hold_stale_external_work(db, tenant_id=user.tenant_id, now=now)
        db.commit()
        assert counts["events"] >= 1
        assert counts["approvals"] >= 1
        assert old_event.delivery_status == "held"
        assert fresh_event.delivery_status == "pending"
        assert expired.status == "held"
        assert current.status == "pending"
        assert db.get(DomainEvent, old_event.id) is not None
        assert db.get(AIApproval, expired.id) is not None
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == user.tenant_id,
                AuditLog.action == "external_work.hold",
                AuditLog.entity_id == str(old_event.id),
            )
        )
        assert audit is not None
        marked = DomainEvent(
            tenant_id=user.tenant_id,
            event_type="lead.created",
            entity_type="lead",
            entity_id=str(uuid4()),
            delivery_status="pending",
            processed_at=now - timedelta(days=20),
            created_at=now - timedelta(days=20),
        )
        db.add(marked)
        db.commit()
        again = hold_stale_external_work(db, tenant_id=user.tenant_id, now=now)
        db.commit()
        assert again["events"] >= 1
        assert marked.delivery_status == "held"
        assert db.get(DomainEvent, marked.id) is not None
    finally:
        db.close()


def test_worker_heartbeat_file_rejects_a_stale_stamp(tmp_path: Path) -> None:
    path = tmp_path / "worker-heartbeat"
    path.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
    assert worker_heartbeat_fresh(path) is True
    path.write_text((datetime.now(UTC) - timedelta(minutes=5)).isoformat(), encoding="utf-8")
    assert worker_heartbeat_fresh(path) is False
    path.write_text("not-a-time", encoding="utf-8")
    assert worker_heartbeat_fresh(path) is False


def test_start_requires_an_explicit_offer_and_keeps_it(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.services.marketing._latest_plan", lambda *_args, **_kwargs: None)
    headers = login(client)
    db = get_session()
    try:
        before = int(db.scalar(select(func.count()).select_from(OperatingPlan)) or 0)
    finally:
        db.close()
    missing = client.post("/api/v1/operating-plans/start", headers=headers)
    assert missing.status_code == 200, missing.text
    assert "not selected automatically" in missing.json()["data"]["detail"]
    db = get_session()
    try:
        after = int(db.scalar(select(func.count()).select_from(OperatingPlan)) or 0)
    finally:
        db.close()
    assert after == before
    monkeypatch.undo()

    headers = login(client)
    unique = f"Unselected offer {uuid4().hex[:8]}"
    created = client.post(
        "/api/v1/content/products",
        headers=headers,
        json={"sku": f"unselected-{uuid4().hex[:8]}", "name": unique, "description": "This offer must not replace the open plan."},
    )
    assert created.status_code == 200, created.text
    db = get_session()
    try:
        user = _user(db)
        plan = db.scalar(
            select(OperatingPlan)
            .where(
                OperatingPlan.tenant_id == user.tenant_id,
                OperatingPlan.deleted_at.is_(None),
                OperatingPlan.status.in_(["running", "blocked", "paused"]),
            )
            .order_by(OperatingPlan.created_at.desc())
        )
        if plan is None:
            chosen = client.post(
                "/api/v1/content/products",
                headers=headers,
                json={
                    "sku": f"chosen-{uuid4().hex[:8]}",
                    "name": f"Chosen offer {uuid4().hex[:8]}",
                    "description": "The selected offer description.",
                },
            )
            assert chosen.status_code == 200, chosen.text
            started = client.post(
                "/api/v1/operating-plans/start",
                headers=headers,
                params={"product_id": chosen.json()["data"]["id"]},
            )
            assert started.status_code == 200, started.text
            plan = db.scalar(
                select(OperatingPlan)
                .where(
                    OperatingPlan.tenant_id == user.tenant_id,
                    OperatingPlan.deleted_at.is_(None),
                    OperatingPlan.status.in_(["running", "blocked", "paused"]),
                )
                .order_by(OperatingPlan.created_at.desc())
            )
        assert plan is not None and plan.product_id is not None
        selected = plan.product_id
        product = db.get(Product, selected)
        assert product is not None
        original = product.description
    finally:
        db.close()
    kept = client.post(
        "/api/v1/operating-plans/start",
        headers=headers,
        params={"product_id": created.json()["data"]["id"]},
    )
    assert kept.status_code == 200, kept.text
    assert "selected product was kept" in kept.json()["data"]["detail"]
    db = get_session()
    try:
        user = _user(db)
        plan = db.scalar(
            select(OperatingPlan)
            .where(
                OperatingPlan.tenant_id == user.tenant_id,
                OperatingPlan.deleted_at.is_(None),
                OperatingPlan.status.in_(["running", "blocked", "paused"]),
            )
            .order_by(OperatingPlan.created_at.desc())
        )
        assert plan is not None
        assert plan.product_id == selected
        product = db.get(Product, selected)
        assert product is not None
        product.description = "EDITED DESCRIPTION SHOULD NOT APPEAR"
        db.commit()
    finally:
        db.close()
    drafted = client.post("/api/v1/operating-plans/drafts", headers=headers)
    assert drafted.status_code == 200, drafted.text
    db = get_session()
    try:
        user = _user(db)
        plan = db.scalar(
            select(OperatingPlan)
            .where(
                OperatingPlan.tenant_id == user.tenant_id,
                OperatingPlan.deleted_at.is_(None),
                OperatingPlan.status.in_(["running", "blocked", "paused"]),
            )
            .order_by(OperatingPlan.created_at.desc())
        )
        assert plan is not None
        body = db.scalar(
            select(CreativeVersion.body)
            .where(CreativeVersion.plan_id == plan.id, CreativeVersion.deleted_at.is_(None))
            .order_by(CreativeVersion.version_number.desc())
        )
        assert body is not None
        assert unique not in body
        assert "EDITED DESCRIPTION SHOULD NOT APPEAR" not in body
        product = db.get(Product, selected)
        assert product is not None
        product.description = original
        db.commit()
    finally:
        db.close()


def test_automated_responders_stop_and_do_not_send(client: TestClient, monkeypatch) -> None:
    headers = login(client)
    email = f"loop.{uuid4().hex[:8]}@buyer.example"
    captured = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={
            "first_name": "Loop",
            "last_name": "Buyer",
            "email": email,
            "company_name": "Loop Co",
            "consent_email": True,
            "source": "inbound",
            "request_note": "Please reply to a person.",
        },
    )
    assert captured.status_code == 200, captured.text
    lead_id = captured.json()["data"]["lead"]["id"]
    db = get_session()
    try:
        user = _user(db)
        lead = db.get(Lead, UUID(lead_id))
        assert lead is not None
        conversation = Conversation(
            tenant_id=user.tenant_id,
            created_by=user.id,
            channel="email",
            lead_id=lead.id,
            subject="Re: enquiry",
            status="open",
            provider_thread_id="thread-loop",
        )
        db.add(conversation)
        db.flush()
        first = EmailMessage(
            tenant_id=user.tenant_id,
            created_by=user.id,
            conversation_id=conversation.id,
            direction="inbound",
            from_addr="automation@responder-a.example",
            to_addrs="[]",
            subject="Automatic reply",
            body_text="This is an automated message. Do not reply.",
            provider="gmail",
            provider_message_id=f"auto-a-{uuid4().hex}",
            provider_thread_id="thread-loop",
            status="SENT",
            lead_id=lead.id,
            header_json='{"auto-submitted": "auto-replied"}',
        )
        second = EmailMessage(
            tenant_id=user.tenant_id,
            created_by=user.id,
            conversation_id=conversation.id,
            direction="inbound",
            from_addr="noreply@buyer.example",
            to_addrs="[]",
            subject="Automatic reply",
            body_text="This is an automated message from the other responder.",
            provider="gmail",
            provider_message_id=f"auto-b-{uuid4().hex}",
            provider_thread_id="thread-loop",
            status="SENT",
            lead_id=lead.id,
            header_json='{"auto-submitted": "auto-replied"}',
        )
        db.add(first)
        db.commit()
        assert route_reply(db, tenant_id=user.tenant_id, actor_id=user.id, lead=lead, message=first, classification={}) == "automated_ignored"
        assert route_reply(db, tenant_id=user.tenant_id, actor_id=user.id, lead=lead, message=first, classification={}) == "automated_ignored"
        db.add(second)
        db.commit()
        assert route_reply(db, tenant_id=user.tenant_id, actor_id=user.id, lead=lead, message=second, classification={}) == "loop_stopped"
        assert conversation.status == "loop_stopped"
        outbound = db.scalar(
            select(func.count())
            .select_from(EmailMessage)
            .where(EmailMessage.conversation_id == conversation.id, EmailMessage.direction == "outbound")
        )
        assert outbound == 0
        approval = AIApproval(
            tenant_id=user.tenant_id,
            created_by=user.id,
            action_level=2,
            action_type="email.send",
            title="Would-be loop reply",
            payload_json='{"thread_id": "thread-loop", "subject": "Re: enquiry", "body": "Still here"}',
            status="approved",
            entity_type="lead",
            entity_id=str(lead.id),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(approval)
        db.commit()

        def fail_provider(*_args, **_kwargs):
            raise AssertionError("provider was called")

        monkeypatch.setattr("app.services.email_send.get_email_provider", fail_provider)
        result = execute_email_send(db, tenant_id=user.tenant_id, actor_id=user.id, approval=approval)
        assert "Automated exchange stopped" in result
    finally:
        db.close()


def test_prepared_scope_blocks_external_execution(client: TestClient, monkeypatch) -> None:
    headers = login(client)
    email = f"scope.{uuid4().hex[:8]}@buyer.example"
    captured = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={
            "first_name": "Scope",
            "last_name": "Buyer",
            "email": email,
            "company_name": "Scope Co",
            "consent_email": True,
            "source": "inbound",
            "request_note": "A person wrote this.",
        },
    )
    lead_id = captured.json()["data"]["lead"]["id"]
    db = get_session()
    scope = None
    try:
        user = _user(db)
        scope = DemoScope(
            tenant_id=user.tenant_id,
            created_by=user.id,
            buyer_email="controlled.buyer@example.com",
            channel="linkedin",
            action_limit=4,
            status="prepared",
            expires_at=datetime.now(UTC) + timedelta(days=2),
            notes="Fixture scope. Not a live authorization.",
        )
        db.add(scope)
        db.commit()
        lead = db.get(Lead, UUID(lead_id))
        assert lead is not None
        approval = AIApproval(
            tenant_id=user.tenant_id,
            created_by=user.id,
            action_level=2,
            action_type="email.send",
            title="Scoped send",
            payload_json='{"subject": "Hello", "body": "Hello"}',
            status="approved",
            entity_type="lead",
            entity_id=str(lead.id),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(approval)
        db.commit()

        def fail_provider(*_args, **_kwargs):
            raise AssertionError("provider was called")

        monkeypatch.setattr("app.services.email_send.get_email_provider", fail_provider)
        prepared = execute_email_send(db, tenant_id=user.tenant_id, actor_id=user.id, approval=approval)
        assert "has not been authorized" in prepared
        scope.status = "authorized"
        db.commit()
        refused = execute_email_send(db, tenant_id=user.tenant_id, actor_id=user.id, approval=approval)
        assert "outside the controlled demonstration" in refused
        assert "Ads and voice" in external_execution_block(db, tenant_id=user.tenant_id, action="ads.launch")
        assert "Ads and voice" in external_execution_block(db, tenant_id=user.tenant_id, action="voice.dial")
    finally:
        if scope is not None:
            scope.status = "closed"
            db.commit()
        db.close()


def test_send_rejects_a_changed_content_version(client: TestClient, monkeypatch) -> None:
    headers = login(client)
    email = f"version.{uuid4().hex[:8]}@buyer.example"
    captured = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={
            "first_name": "Version",
            "last_name": "Buyer",
            "email": email,
            "company_name": "Version Co",
            "consent_email": True,
            "source": "inbound",
            "request_note": "A person wrote this.",
        },
    )
    lead_id = captured.json()["data"]["lead"]["id"]
    db = get_session()
    try:
        user = _user(db)
        approval = AIApproval(
            tenant_id=user.tenant_id,
            created_by=user.id,
            action_level=2,
            action_type="email.send",
            title="Versioned send",
            payload_json='{"subject": "Hello", "body": "Changed", "copy_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            status="approved",
            entity_type="lead",
            entity_id=lead_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(approval)
        db.commit()

        def fail_provider(*_args, **_kwargs):
            raise AssertionError("provider was called")

        monkeypatch.setattr("app.services.email_send.get_email_provider", fail_provider)
        result = execute_email_send(db, tenant_id=user.tenant_id, actor_id=user.id, approval=approval)
        assert "content version" in result
    finally:
        db.close()


def test_replay_does_not_release_held_work(client: TestClient) -> None:
    _ = client
    db = get_session()
    try:
        user = _user(db)
        event = DomainEvent(
            tenant_id=user.tenant_id,
            event_type="lead.created",
            entity_type="lead",
            entity_id=str(uuid4()),
            delivery_status="held",
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        db.add(event)
        db.commit()
        message = replay_event(db, event, actor_id=user.id)
        assert "stays in review" in message
        assert event.delivery_status == "held"
    finally:
        db.close()


def test_stale_retry_is_held_before_a_provider_call(client: TestClient, monkeypatch) -> None:
    _ = client
    db = get_session()
    try:
        user = _user(db)
        now = datetime.now(UTC)
        conversation = Conversation(
            tenant_id=user.tenant_id,
            created_by=user.id,
            channel="email",
            subject="Old send",
            status="open",
        )
        approval = AIApproval(
            tenant_id=user.tenant_id,
            created_by=user.id,
            action_level=2,
            action_type="email.send",
            title="Stale retry",
            payload_json='{"subject": "Hello", "body": "Hello"}',
            status="approved",
            expires_at=now + timedelta(days=1),
        )
        db.add_all([conversation, approval])
        db.flush()
        message = EmailMessage(
            tenant_id=user.tenant_id,
            created_by=user.id,
            conversation_id=conversation.id,
            direction="outbound",
            from_addr="sender@example.com",
            to_addrs="[]",
            subject="Hello",
            body_text="Hello",
            provider="gmail",
            provider_message_id=f"stale-retry-{uuid4().hex}",
            status="RETRYING",
            approval_id=approval.id,
            created_at=now - timedelta(days=30),
            next_retry_at=now - timedelta(days=30),
        )
        db.add(message)
        db.commit()

        def fail_provider(*_args, **_kwargs):
            raise AssertionError("provider was called")

        monkeypatch.setattr("app.services.email_send.get_email_provider", fail_provider)
        assert retry_retrying_sends(db, tenant_id=user.tenant_id) == 0
        assert message.status == "HELD"
        assert db.get(EmailMessage, message.id) is not None
    finally:
        db.close()


def test_acknowledgement_grant_does_not_release_other_email(client: TestClient) -> None:
    _ = client
    db = get_session()
    grant = None
    try:
        user = _user(db)
        settings = db.scalar(select(AutopilotSettings).where(AutopilotSettings.tenant_id == user.tenant_id, AutopilotSettings.deleted_at.is_(None)))
        assert settings is not None and settings.email_approval_required
        grant = AuthorizationGrant(
            tenant_id=user.tenant_id,
            created_by=user.id,
            name="One acknowledgement",
            mode="bounded_autopilot",
            workflow="inbound",
            channel="email",
            template_version="email.acknowledge",
            volume_cap=1,
            status="active",
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
        db.add(grant)
        db.commit()
        assert send_authorization(db, tenant_id=user.tenant_id, settings=settings, action_type="email.acknowledge") == "execute"
        assert send_authorization(db, tenant_id=user.tenant_id, settings=settings, action_type="email.send") == "approval"
        assert send_authorization(db, tenant_id=user.tenant_id, settings=settings, action_type="sequence.email.send") == "approval"
    finally:
        if grant is not None:
            grant.status = "revoked"
            db.commit()
        db.close()


def test_bound_scope_reopens_when_its_buyer_changes(client: TestClient) -> None:
    _ = client
    db = get_session()
    scope = None
    try:
        user = _user(db)
        scope = DemoScope(
            tenant_id=user.tenant_id,
            created_by=user.id,
            buyer_email="controlled.buyer@example.com",
            sender_mailbox="sender@example.com",
            channel="linkedin",
            action_limit=4,
            status="authorized",
            allowed_actions=json.dumps(
                {"social.publish": 1, "email.acknowledge": 1, "email.send": 1, "calendar.book": 1}
            ),
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
        db.add(scope)
        db.commit()
        seal_scope(scope)
        db.commit()
        assert (
            external_execution_block(
                db,
                tenant_id=user.tenant_id,
                action="sequence.email.send",
                recipient="controlled.buyer@example.com",
            )
            == "Sequence outreach is outside this demonstration."
        )
        assert (
            external_execution_block(
                db,
                tenant_id=user.tenant_id,
                action="email.acknowledge",
                recipient="controlled.buyer@example.com",
            )
            == ""
        )
        scope.buyer_email = "other@example.com"
        db.commit()
        blocked = external_execution_block(
            db,
            tenant_id=user.tenant_id,
            action="email.acknowledge",
            recipient="other@example.com",
        )
        assert "reviewed again" in blocked
        assert scope.status == "prepared"
    finally:
        if scope is not None:
            scope.status = "closed"
            db.commit()
        db.close()


def test_combined_offer_draft_keeps_the_product_name_and_saved_prices(client: TestClient) -> None:
    headers = login(client)
    setup = client.post(
        "/api/v1/content/products",
        headers=headers,
        json={"sku": f"setup-{uuid4().hex[:6]}", "name": "One-time setup, under 200 employees", "description": "One-time setup of ₹3,00,000 for a company under 200 employees.", "kind": "one_time", "list_price": "300000.00", "currency": "INR"},
    )
    monthly = client.post(
        "/api/v1/content/products",
        headers=headers,
        json={"sku": f"monthly-{uuid4().hex[:6]}", "name": "Revenue OS monthly", "description": "Starting monthly price of ₹50,000 for a company of about 50 to 200 employees.", "kind": "subscription", "list_price": "50000.00", "currency": "INR"},
    )
    assert setup.status_code == 200, setup.text
    assert monthly.status_code == 200, monthly.text
    setup_id = setup.json()["data"]["id"]
    db = get_session()
    plan = None
    try:
        user = _user(db)
        for open_plan in db.scalars(select(OperatingPlan).where(OperatingPlan.tenant_id == user.tenant_id, OperatingPlan.deleted_at.is_(None), OperatingPlan.status.in_(["running", "blocked", "paused"]))).all():
            open_plan.status = "completed"
        plan = OperatingPlan(
            tenant_id=user.tenant_id,
            created_by=user.id,
            product_id=UUID(setup_id),
            channel="linkedin",
            audience="India B2B revenue teams · technology,software · india · CEO,Founder,CRO",
            status="running",
            next_action="generate_draft",
            context_snapshot=json.dumps(
                {
                    "name": "Autonomous Revenue OS",
                    "description": "One workspace runs the revenue cycle. Autopilot prepares the work. A person approves send, spend, and dial.",
                    "customer_audience": "Founders, CEOs, CROs, and revenue leaders at B2B companies in India with a sales team",
                    "offer_lines": [
                        {"description": "One-time setup of ₹3,00,000 for a company under 200 employees."},
                        {"description": "Starting monthly price of ₹50,000 for a company of about 50 to 200 employees."},
                    ],
                }
            ),
        )
        db.add(plan)
        db.commit()
        result = generate_draft(db, tenant_id=user.tenant_id, actor_id=user.id)
        db.commit()
        version = db.get(CreativeVersion, UUID(result["version_id"]))
        assert version is not None
        assert version.status == "draft"
        assert version.headline == "Autonomous Revenue OS"
        assert "INR 300,000" in version.body
        assert "under 200 employees" in version.body
        assert "₹50,000" not in version.body
        assert "50,000" not in version.body
        assert "50000" not in version.body
        assert "200 to 1,000" not in version.body
        assert "One-time setup, under 200 employees" not in version.headline
        assert "GOV" not in version.headline
        assert "For Founders, CEOs, CROs, and revenue leaders at B2B companies in India with a sales team." in version.body
        assert "technology,software" not in version.body
    finally:
        if plan is not None:
            plan.status = "completed"
            db.commit()
        db.close()


def test_prepared_scope_does_not_approve_or_send_the_acknowledgement(client: TestClient, mock_providers: None) -> None:
    _ = mock_providers
    headers = login(client)
    settings = client.patch(
        "/api/v1/autonomy/settings",
        headers=headers,
        json={"enabled": True, "quiet_hours_start": "00:00", "quiet_hours_end": "00:00"},
    )
    assert settings.status_code == 200, settings.text
    email = f"prepared.{uuid4().hex[:8]}@example.com"
    db = get_session()
    scope_id = None
    grant_id = None
    try:
        user = _user(db)
        scope = DemoScope(
            tenant_id=user.tenant_id,
            created_by=user.id,
            channel="linkedin",
            buyer_email=email,
            sender_mailbox="sender@example.com",
            action_limit=3,
            status="prepared",
            expires_at=datetime.now(UTC) + timedelta(hours=72),
            allowed_actions=json.dumps({"email.acknowledge": 1, "email.send": 1, "calendar.book": 1}),
        )
        grant = AuthorizationGrant(
            tenant_id=user.tenant_id,
            created_by=user.id,
            name="Prepared acknowledgement check",
            mode="bounded_autopilot",
            workflow="inbound",
            channel="email",
            template_version="email.acknowledge",
            volume_cap=1,
            status="active",
            expires_at=datetime.now(UTC) + timedelta(hours=72),
        )
        db.add(scope)
        db.add(grant)
        db.commit()
        scope_id = scope.id
        grant_id = grant.id
    finally:
        db.close()
    captured = client.post(
            "/api/v1/acquisition/capture",
            headers=headers,
            json={
                "first_name": "Buyer",
                "last_name": "Enquiry",
                "email": email,
                "company_name": "Local Test",
                "consent_email": True,
                "source": "inbound",
                "request_note": "We want to see the revenue workspace.",
            },
        )
    try:
        assert captured.status_code == 200, captured.text
        lead_id = captured.json()["data"]["lead"]["id"]
        process_outbox()
        process_outbox()
        db = get_session()
        try:
            messages = db.scalars(
                select(EmailMessage).where(EmailMessage.lead_id == UUID(lead_id), EmailMessage.direction == "outbound")
            ).all()
            assert list(messages) == []
            approval = db.scalar(
                select(AIApproval).where(
                    AIApproval.entity_id == lead_id,
                    AIApproval.action_type == "email.acknowledge",
                    AIApproval.deleted_at.is_(None),
                )
            )
            assert approval is not None
            assert approval.status == "pending"
        finally:
            db.close()
    finally:
        db = get_session()
        try:
            scope = db.get(DemoScope, scope_id) if scope_id is not None else None
            grant = db.get(AuthorizationGrant, grant_id) if grant_id is not None else None
            if scope is not None:
                scope.status = "closed"
            if grant is not None:
                grant.status = "revoked"
            db.commit()
        finally:
            db.close()
