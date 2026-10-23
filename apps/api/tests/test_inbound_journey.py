"""Fixture journey from enquiry to discovery meeting. No live provider calls."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import get_session
from app.models.ai import AIApproval
from app.models.assessment import AssessmentEvidence, ExternalEffect
from app.models.autonomy import AutonomousRun
from app.models.crm import Lead, Opportunity, Task
from app.models.execution import AuthorizationGrant
from app.models.identity import DomainEvent, User
from app.models.integrations import EmailMessage, ProviderInboxEvent
from app.models.lifecycle import MeetingRecord, SequenceEnrollment
from app.providers.email import InboundEmail, MockEmailProvider
from app.services.effects import EffectAttempt, ReconciledEffect, execute_external_effect
from app.services.inbox import process_inbox_event, sync_inbound_for_tenant
from app.services.outbox_notify import notify_outbox
from app.workers.celery_app import process_outbox
from tests.conftest import login


def _user(db) -> User:
    user = db.scalar(select(User).where(User.email == "admin@agrayian.demo"))
    assert user is not None
    return user


def _quiet_off(client: TestClient, headers: dict) -> None:
    response = client.patch(
        "/api/v1/autonomy/settings",
        headers=headers,
        json={"enabled": True, "quiet_hours_start": "00:00", "quiet_hours_end": "00:00"},
    )
    assert response.status_code == 200, response.text


@pytest.fixture(autouse=True)
def _isolate_shared_tenant(client: TestClient):
    headers = login(client)
    before = client.get("/api/v1/autonomy/settings", headers=headers).json()["data"]
    yield
    db = get_session()
    try:
        rows = db.scalars(
            select(AuthorizationGrant).where(
                AuthorizationGrant.name == "Inbound acknowledgement",
                AuthorizationGrant.status == "active",
            )
        ).all()
        for row in rows:
            row.status = "revoked"
        db.commit()
    finally:
        db.close()
    client.patch(
        "/api/v1/autonomy/settings",
        headers=headers,
        json={
            "enabled": before.get("enabled", True),
            "quiet_hours_start": before.get("quiet_hours_start") or "21:00",
            "quiet_hours_end": before.get("quiet_hours_end") or "08:00",
        },
    )


def _grant(db, user: User) -> None:
    db.add(
        AuthorizationGrant(
            tenant_id=user.tenant_id,
            created_by=user.id,
            name="Inbound acknowledgement",
            mode="bounded_autopilot",
            workflow="inbound",
            channel="email",
            status="active",
            volume_cap=20,
        )
    )
    db.commit()


def _capture(client: TestClient, headers: dict, email: str, note: str) -> str:
    response = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={
            "first_name": "Buyer",
            "last_name": "Enquiry",
            "email": email,
            "company_name": "North Parcel",
            "consent_email": True,
            "source": "inbound",
            "request_note": note,
        },
    )
    assert response.status_code == 200, response.text
    lead = response.json()["data"]["lead"]
    assert lead and lead["id"]
    return lead["id"]


def test_low_score_enquiry_sends_one_acknowledgement_and_not_a_sequence(client: TestClient, mock_providers: None) -> None:
    _ = mock_providers
    headers = login(client)
    _quiet_off(client, headers)
    db = get_session()
    try:
        _grant(db, _user(db))
    finally:
        db.close()
    email = f"ack.{uuid4().hex[:8]}@northparcel.example"
    lead_id = _capture(client, headers, email, "We need help with dispatch.")
    db = get_session()
    try:
        pending = db.scalar(
            select(func.count()).select_from(DomainEvent).where(
                DomainEvent.entity_id == lead_id,
                DomainEvent.delivery_status == "pending",
            )
        )
        assert pending >= 1
    finally:
        db.close()
    process_outbox()
    process_outbox()
    db = get_session()
    try:
        messages = db.scalars(
            select(EmailMessage).where(EmailMessage.lead_id == UUID(lead_id), EmailMessage.direction == "outbound")
        ).all()
        assert len(messages) == 1
        assert messages[0].status == "SENT"
        assert messages[0].provider_message_id.startswith("mock-email-")
        sent = db.scalar(
            select(func.count()).select_from(DomainEvent).where(
                DomainEvent.entity_id == lead_id,
                DomainEvent.event_type == "response.sent",
            )
        )
        assert sent == 1
        enrollment = db.scalar(select(SequenceEnrollment).where(SequenceEnrollment.lead_id == UUID(lead_id)))
        assert enrollment is None
        run = db.scalar(select(AutonomousRun).where(AutonomousRun.trigger_event == f"lead:{lead_id}"))
        assert run is not None
        assert run.status == "completed"
        run_id = str(run.id)
    finally:
        db.close()
    operations = client.get("/api/v1/command-center/operations", headers=headers)
    assert operations.status_code == 200, operations.text
    view = operations.json()["data"]
    assert any(row["lead_email"] == email for row in view["journeys"])
    assert view["outcomes"]["responses_sent"] >= 1
    assert "queue_age_seconds" in view
    assert "scheduler" in view
    preview = client.get(f"/api/v1/journeys/{run_id}/next-action", headers=headers)
    assert preview.status_code == 200, preview.text
    readiness = client.get("/api/v1/operating-plans/readiness", headers=headers, params={"channel": "email"})
    assert readiness.status_code == 200, readiness.text
    checks = {row["name"]: row["status"] for row in readiness.json()["data"]["checks"]}
    assert "mailbox" in checks
    idempotency_key = "continue-ack-once"
    first = client.post(
        f"/api/v1/journeys/{run_id}/continue",
        headers={**headers, "Idempotency-Key": idempotency_key},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/v1/journeys/{run_id}/continue",
        headers={**headers, "Idempotency-Key": idempotency_key},
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["job_id"] == first.json()["data"]["job_id"]
    assert second.json()["data"]["detail"] == "Replayed."


def test_failed_notify_is_recovered_once_by_the_outbox_beat(client: TestClient, mock_providers: None, monkeypatch) -> None:
    _ = mock_providers
    headers = login(client)
    _quiet_off(client, headers)
    db = get_session()
    try:
        _grant(db, _user(db))
    finally:
        db.close()
    email = f"beat.{uuid4().hex[:8]}@northparcel.example"
    lead_id = _capture(client, headers, email, "Please acknowledge this enquiry.")
    from app.core.config import get_settings
    from app.workers.celery_app import celery_app

    monkeypatch.setattr(get_settings(), "environment", "development")

    def fail_task(name: str) -> None:
        assert name == "process_outbox"
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(celery_app, "send_task", fail_task)
    notify_outbox()
    db = get_session()
    try:
        still_pending = db.scalar(
            select(func.count()).select_from(DomainEvent).where(
                DomainEvent.entity_id == lead_id,
                DomainEvent.delivery_status == "pending",
            )
        )
        assert still_pending >= 1
    finally:
        db.close()
    process_outbox()
    process_outbox()
    db = get_session()
    try:
        messages = db.scalars(
            select(EmailMessage).where(EmailMessage.lead_id == UUID(lead_id), EmailMessage.direction == "outbound")
        ).all()
        assert len(messages) == 1
        pending = db.scalar(
            select(func.count()).select_from(DomainEvent).where(
                DomainEvent.entity_id == lead_id,
                DomainEvent.event_type == "lead.created",
                DomainEvent.delivery_status == "pending",
            )
        )
        assert pending == 0
    finally:
        db.close()


def test_successful_notify_wakes_the_worker_without_a_second_send(client: TestClient, mock_providers: None, monkeypatch) -> None:
    _ = mock_providers
    headers = login(client)
    _quiet_off(client, headers)
    db = get_session()
    try:
        _grant(db, _user(db))
    finally:
        db.close()
    email = f"wake.{uuid4().hex[:8]}@northparcel.example"
    lead_id = _capture(client, headers, email, "Please acknowledge this enquiry.")
    from app.core.config import get_settings
    from app.workers.celery_app import celery_app

    seen: list[str] = []

    def wake(name: str) -> None:
        seen.append(name)
        process_outbox()

    monkeypatch.setattr(get_settings(), "environment", "development")
    monkeypatch.setattr(celery_app, "send_task", wake)
    notify_outbox()
    notify_outbox()
    db = get_session()
    try:
        messages = db.scalars(
            select(EmailMessage).where(EmailMessage.lead_id == UUID(lead_id), EmailMessage.direction == "outbound")
        ).all()
        assert seen == ["process_outbox", "process_outbox"]
        assert len(messages) == 1
        assert messages[0].status == "SENT"
    finally:
        db.close()


def _inbound_reply(client: TestClient, headers: dict, body: str) -> str:
    MockEmailProvider.inbox.clear()
    email = f"reply.{uuid4().hex[:8]}@northparcel.example"
    lead_id = _capture(client, headers, email, "We need help with dispatch.")
    process_outbox()
    MockEmailProvider.inbox.append(
        InboundEmail(
            provider_message_id=f"reply-{uuid4().hex}",
            thread_id="thread-policy",
            from_addr=email,
            to_addrs=["hello@example.com"],
            subject="Re: enquiry",
            body_text=body,
            received_at=datetime.now(UTC),
        )
    )
    db = get_session()
    try:
        user = _user(db)
        assert sync_inbound_for_tenant(db, tenant_id=user.tenant_id, actor_id=user.id) == 1
        db.commit()
    finally:
        db.close()
        MockEmailProvider.inbox.clear()
    process_outbox()
    process_outbox()
    return lead_id


def test_reply_policies_stop_followups_without_duplicate_evidence(client: TestClient, mock_providers: None) -> None:
    _ = mock_providers
    headers = login(client)
    _quiet_off(client, headers)
    db = get_session()
    try:
        user = _user(db)
        _grant(db, user)
    finally:
        db.close()

    opted_out = _inbound_reply(client, headers, "Please unsubscribe me from this list.")
    db = get_session()
    try:
        lead = db.get(Lead, UUID(opted_out))
        assert lead is not None
        assert lead.opt_out is True
        assert lead.consent_email is False
    finally:
        db.close()

    paused = _inbound_reply(client, headers, "I am out of office until Monday.")
    trace = client.get(f"/api/v1/autonomy/entities/lead/{paused}", headers=headers).json()["data"]
    assert trace["state"] == "PAUSED"

    wrong = _inbound_reply(client, headers, "I am the wrong person for this.")
    trace = client.get(f"/api/v1/autonomy/entities/lead/{wrong}", headers=headers).json()["data"]
    assert trace["state"] == "BLOCKED"

    email = f"ask.{uuid4().hex[:8]}@northparcel.example"
    asked = _capture(client, headers, email, "We need help with dispatch.")
    process_outbox()
    db = get_session()
    try:
        user = _user(db)
        db.add(
            AIApproval(
                tenant_id=user.tenant_id,
                created_by=user.id,
                action_level=2,
                action_type="sequence.email.send",
                title="Queued follow-up",
                payload_json="{}",
                status="pending",
                entity_type="lead",
                entity_id=asked,
                idempotency_key=f"sequence-followup:{asked}",
            )
        )
        db.commit()
    finally:
        db.close()
    MockEmailProvider.inbox.clear()
    MockEmailProvider.inbox.append(
        InboundEmail(
            provider_message_id=f"ask-{uuid4().hex}",
            thread_id="thread-question",
            from_addr=email,
            to_addrs=["hello@example.com"],
            subject="Re: enquiry",
            body_text="What does onboarding cost?",
            received_at=datetime.now(UTC),
        )
    )
    db = get_session()
    try:
        user = _user(db)
        assert sync_inbound_for_tenant(db, tenant_id=user.tenant_id, actor_id=user.id) == 1
        db.commit()
    finally:
        db.close()
        MockEmailProvider.inbox.clear()
    process_outbox()
    process_outbox()
    db = get_session()
    try:
        followup = db.scalar(
            select(AIApproval).where(AIApproval.entity_id == asked, AIApproval.action_type == "sequence.email.send")
        )
        assert followup is not None
        assert followup.status == "cancelled"
        acknowledgement = db.scalar(
            select(AIApproval).where(AIApproval.entity_id == asked, AIApproval.action_type == "email.acknowledge")
        )
        assert acknowledgement is not None
        assert acknowledgement.status == "approved"
        replies = db.scalars(
            select(AIApproval).where(AIApproval.entity_id == asked, AIApproval.action_type == "email.send", AIApproval.title.startswith("Reply"))
        ).all()
        assert len(replies) == 1
        evidence = db.scalar(
            select(func.count()).select_from(AssessmentEvidence).where(AssessmentEvidence.excerpt == "What does onboarding cost?")
        )
        assert evidence == 1
    finally:
        db.close()

    interested = _inbound_reply(client, headers, "I am interested. Tell me more.")
    db = get_session()
    try:
        lead = db.get(Lead, UUID(interested))
        assert lead is not None
        assert lead.opt_out is False
        evidence = db.scalar(
            select(func.count()).select_from(AssessmentEvidence).where(
                AssessmentEvidence.excerpt == "I am interested. Tell me more."
            )
        )
        assert evidence == 1
    finally:
        db.close()


def test_reply_can_book_discovery_before_sales_qualification(client: TestClient, mock_providers: None) -> None:
    _ = mock_providers
    headers = login(client)
    _quiet_off(client, headers)
    db = get_session()
    try:
        user = _user(db)
        _grant(db, user)
    finally:
        db.close()
    email = f"meet.{uuid4().hex[:8]}@northparcel.example"
    lead_id = _capture(client, headers, email, "We need help with dispatch.")
    process_outbox()
    MockEmailProvider.inbox.append(
        InboundEmail(
            provider_message_id=f"reply-{uuid4().hex}",
            thread_id="thread-discovery",
            from_addr=email,
            to_addrs=["hello@example.com"],
            subject="Re: enquiry",
            body_text="Can we meet next Tuesday?",
            received_at=datetime.now(UTC),
        )
    )
    db = get_session()
    try:
        user = _user(db)
        synced = sync_inbound_for_tenant(db, tenant_id=user.tenant_id, actor_id=user.id)
        assert synced == 1
        db.commit()
    finally:
        db.close()
        MockEmailProvider.inbox.clear()
    process_outbox()
    db = get_session()
    try:
        user = _user(db)
        lead = db.get(Lead, UUID(lead_id))
        assert lead is not None
        proposals = client.get("/api/v1/ai/approvals", headers=headers).json()["data"]
        proposal = next(
            row
            for row in proposals
            if row.get("entity_id") == lead_id and "slots" in json.loads(row.get("payload_json") or "{}")
        )
        slots = json.loads(proposal["payload_json"])["slots"]
        assert len(slots) >= 1
        before = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.tenant_id == user.tenant_id))
    finally:
        db.close()
    booked = client.post(
        f"/api/v1/leads/{lead_id}/discovery-booking",
        headers=headers,
        json={"start_at": slots[0]["start"], "end_at": slots[0]["end"], "timezone": slots[0]["timezone"]},
    )
    assert booked.status_code == 200, booked.text
    body = booked.json()["data"]
    assert body["status"] == "booked"
    assert body["provider_event_id"]
    db = get_session()
    try:
        user = _user(db)
        meeting = db.get(MeetingRecord, UUID(body["meeting_id"]))
        assert meeting is not None
        assert meeting.provider_event_id == body["provider_event_id"]
        assert "attendees" in meeting.insights_json
        after = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.tenant_id == user.tenant_id))
        assert after == before
    finally:
        db.close()
    facts = {
        "facts": [
            {"facet": "business_need", "fact_class": "verified", "value": "dispatch", "relation": "present"},
            {"facet": "agreed_next_step", "fact_class": "verified", "value": "discovery complete", "relation": "present"},
            {"facet": "industry", "fact_class": "verified", "value": "logistics", "relation": "match"},
            {"facet": "employees", "fact_class": "verified", "value": "120", "relation": "inside_range"},
        ]
    }
    first = client.post(f"/api/v1/leads/{lead_id}/sales-qualification", headers=headers, json=facts)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["sales_qualified"] is True
    opportunity_id = first.json()["data"]["opportunity_id"]
    assert opportunity_id
    second = client.post(f"/api/v1/leads/{lead_id}/sales-qualification", headers=headers, json=facts)
    assert second.json()["data"]["opportunity_id"] == opportunity_id
    later = datetime.fromisoformat(slots[0]["start"]) + timedelta(days=1)
    later_end = later + timedelta(minutes=30)
    moved = client.post(
        f"/api/v1/journeys/meetings/{body['meeting_id']}/reschedule",
        headers=headers,
        json={"start_at": later.isoformat(), "end_at": later_end.isoformat(), "timezone": "UTC"},
    )
    assert moved.status_code == 200, moved.text
    db = get_session()
    try:
        meeting = db.get(MeetingRecord, UUID(body["meeting_id"]))
        assert meeting is not None
        assert meeting.status == "rescheduled"
        assert meeting.provider_event_id == body["provider_event_id"]
    finally:
        db.close()


def test_uncertain_reply_is_one_review_task(client: TestClient, mock_providers: None) -> None:
    _ = mock_providers
    headers = login(client)
    _quiet_off(client, headers)
    email = f"unsure.{uuid4().hex[:8]}@northparcel.example"
    lead_id = _capture(client, headers, email, "We need help with dispatch.")
    process_outbox()
    message_id = f"unsure-{uuid4().hex}"
    MockEmailProvider.inbox.append(
        InboundEmail(
            provider_message_id=message_id,
            thread_id="thread-unsure",
            from_addr=email,
            to_addrs=["hello@example.com"],
            subject="Note",
            body_text="Following up on the earlier note.",
            received_at=datetime.now(UTC),
        )
    )
    db = get_session()
    try:
        user = _user(db)
        sync_inbound_for_tenant(db, tenant_id=user.tenant_id, actor_id=user.id)
        event = db.scalar(select(ProviderInboxEvent).where(ProviderInboxEvent.external_id == message_id))
        assert event is not None
        again = process_inbox_event(db, event, actor_id=user.id)
        assert again == "already"
        db.commit()
    finally:
        db.close()
        MockEmailProvider.inbox.clear()
    process_outbox()
    process_outbox()
    db = get_session()
    try:
        user = _user(db)
        evidence = db.scalar(
            select(func.count()).select_from(AssessmentEvidence).where(
                AssessmentEvidence.tenant_id == user.tenant_id,
                AssessmentEvidence.kind == "reply",
                AssessmentEvidence.excerpt == "Following up on the earlier note.",
            )
        )
        tasks = db.scalar(
            select(func.count()).select_from(Task).where(Task.entity_id == lead_id, Task.title == "Review an uncertain reply")
        )
        assert evidence == 1
        assert tasks == 1
    finally:
        db.close()
        MockEmailProvider.inbox.clear()


def test_rate_limit_is_bounded_and_timeout_is_not_a_resend(client: TestClient) -> None:
    _ = client
    db = get_session()
    calls = {"n": 0}

    def limited() -> EffectAttempt:
        calls["n"] += 1
        return EffectAttempt(failed=True, retryable=True, failure_class="RATE_LIMIT", retry_after_seconds=120)

    def reconcile(_row: ExternalEffect) -> ReconciledEffect:
        raise AssertionError("a rate limit is not an unknown outcome")

    try:
        user = _user(db)
        run = AutonomousRun(tenant_id=user.tenant_id, created_by=user.id, status="running", workflow="rate", trigger="manual")
        db.add(run)
        db.flush()
        kwargs = {
            "tenant_id": user.tenant_id,
            "actor_id": user.id,
            "run": run,
            "action": "email.acknowledge",
            "channel": "email",
            "target_id": "person-rate",
            "content_version": "v1",
            "grant_id": "grant-rate",
            "call": limited,
            "reconcile": reconcile,
        }
        first = execute_external_effect(db, **kwargs)
        assert first.outcome == "retry_wait"
        second = execute_external_effect(db, **kwargs)
        assert second.id == first.id
        assert calls["n"] == 1
        detail = first.detail
        assert "120" in detail
        meta = json.loads(first.detail)
        meta["next_attempt_at"] = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
        meta["attempts"] = 1
        first.detail = json.dumps(meta)
        execute_external_effect(db, **kwargs)
        assert calls["n"] == 2
        meta["attempts"] = 3
        meta["next_attempt_at"] = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
        first.detail = json.dumps(meta)
        first.outcome = "retry_wait"
        exhausted = execute_external_effect(db, **kwargs)
        assert exhausted.outcome == "confirmed_failure"
        assert calls["n"] == 2

        timed = {"n": 0}

        def blow() -> EffectAttempt:
            timed["n"] += 1
            raise TimeoutError("accepted then timed out")

        def recover(row: ExternalEffect) -> ReconciledEffect:
            assert row.outcome == "unknown"
            return ReconciledEffect(outcome="confirmed", provider_id="provider-once")

        kwargs["content_version"] = "timeout"
        kwargs["call"] = blow
        kwargs["reconcile"] = recover
        unknown = execute_external_effect(db, **kwargs)
        assert unknown.outcome == "unknown"
        recovered = execute_external_effect(db, **kwargs)
        assert recovered.outcome == "confirmed"
        assert recovered.provider_ref == "provider-once"
        assert timed["n"] == 1
        db.rollback()
    finally:
        db.close()


def test_disconnected_gmail_waits_instead_of_sending(client: TestClient, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "email_provider", "gmail")
    monkeypatch.setattr(get_settings(), "calendar_provider", "mock")
    headers = login(client)
    _quiet_off(client, headers)
    db = get_session()
    try:
        _grant(db, _user(db))
    finally:
        db.close()
    email = f"wait.{uuid4().hex[:8]}@northparcel.example"
    lead_id = _capture(client, headers, email, "We need help with dispatch.")
    process_outbox()
    db = get_session()
    try:
        messages = db.scalars(select(EmailMessage).where(EmailMessage.lead_id == UUID(lead_id))).all()
        assert messages == []
        run = db.scalar(select(AutonomousRun).where(AutonomousRun.trigger_event == f"lead:{lead_id}"))
        assert run is not None
        assert run.status == "waiting_for_configuration"
    finally:
        db.close()
