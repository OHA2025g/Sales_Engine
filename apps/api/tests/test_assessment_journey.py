from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai.providers import MockLLMProvider, NotConfiguredLLMProvider, get_llm_provider
from app.core.config import get_settings
from app.db.session import get_session
from app.models.ai import AIApproval
from app.models.assessment import ExternalEffect
from app.models.autonomy import AutonomousRun, AutonomousRunStep
from app.models.crm import Account, Contact, Lead, Opportunity, Task
from app.models.execution import AuthorizationGrant, JourneyLink
from app.models.identity import DomainEvent, User
from app.providers.ads import MetaAdsProvider, get_ads_provider
from app.services.acquisition import capture_inbound
from app.services.assessment import DEFAULT_SALES_RULES, Fact, decide_assessment
from app.services.effects import EffectAttempt, ReconciledEffect, execute_external_effect
from app.services.ml.catalog import TASKS
from app.services.ml.labels import resolve_label
from app.services.public_forms import create_form_key
from tests.conftest import login


def _user(db) -> User:
    user = db.scalar(select(User).where(User.email == "admin@agrayian.demo"))
    assert user is not None
    return user


def _verified_facts(employee_class: str = "verified") -> list[dict]:
    return [
        {"facet": "business_need", "fact_class": "verified", "value": "dispatch workflow", "relation": "present"},
        {"facet": "agreed_next_step", "fact_class": "verified", "value": "review a proposal", "relation": "present"},
        {"facet": "industry", "fact_class": "verified", "value": "logistics", "relation": "match"},
        {"facet": "employees", "fact_class": employee_class, "value": "120", "relation": "inside_range"},
    ]


def test_sparse_enquiry_stays_response_eligible_without_a_sales_handoff(client: TestClient, mock_providers: None) -> None:
    headers = login(client)
    created = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "first_name": "Incomplete",
            "last_name": "Enquiry",
            "email": f"incomplete.{uuid4().hex[:8]}@parcel-032.example",
            "consent_email": True,
            "notes": "We need help with dispatch.",
            "source": "public_form",
        },
    )
    assert created.status_code == 200, created.text
    lead_id = created.json()["data"]["id"]
    assessment = client.get(f"/api/v1/leads/{lead_id}/assessment", headers=headers)
    assert assessment.status_code == 200, assessment.text
    body = assessment.json()["data"]
    assert body["response_eligible"] is True
    assert body["meeting_eligible"] is False
    assert body["sales_qualified"] is False
    assert body["not_a_fit"] is False
    assert body["next_action"] == "acknowledge"
    assert "probability" not in body
    db = get_session()
    try:
        run = db.scalar(
            select(AutonomousRun).where(
                AutonomousRun.workflow == "lead_intake",
                AutonomousRun.trigger_event == f"lead:{lead_id}",
            )
        )
        assert run is not None
        assert run.status == "WAITING_FOR_APPROVAL"
        acknowledgement = db.scalar(
            select(AIApproval).where(
                AIApproval.entity_id == lead_id,
                AIApproval.action_type == "email.acknowledge",
                AIApproval.deleted_at.is_(None),
            )
        )
        assert acknowledgement is not None
        step = db.scalar(select(AutonomousRunStep).where(AutonomousRunStep.run_id == run.id, AutonomousRunStep.name == "qualify"))
        assert step is not None
        assert step.started_at is not None
        disqualified = db.scalar(
            select(func.count()).select_from(DomainEvent).where(
                DomainEvent.entity_id == lead_id,
                DomainEvent.event_type == "lead.disqualified",
            )
        )
        assert disqualified == 0
    finally:
        db.close()


def test_meeting_request_does_not_open_an_opportunity(client: TestClient, mock_providers: None) -> None:
    headers = login(client)
    created = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "first_name": "Meet",
            "last_name": "Ask",
            "email": f"meet.{uuid4().hex[:8]}@parcel-032.example",
            "consent_email": True,
            "notes": "Can we meet next Tuesday?",
            "source": "public_form",
        },
    )
    assert created.status_code == 200, created.text
    lead_id = created.json()["data"]["id"]
    body = client.get(f"/api/v1/leads/{lead_id}/assessment", headers=headers).json()["data"]
    assert body["meeting_eligible"] is True
    assert body["response_eligible"] is True
    assert body["sales_qualified"] is False
    assert body["next_action"] == "book_discovery_meeting"
    db = get_session()
    try:
        link = db.scalar(
            select(JourneyLink).where(JourneyLink.journey_key == f"lead:{lead_id}", JourneyLink.entity_type == "opportunity")
        )
        assert link is None
    finally:
        db.close()


def test_self_reported_size_is_not_a_verified_fit(client: TestClient) -> None:
    decision = decide_assessment(
        facts=[
            Fact("industry", "verified", "logistics", "match"),
            Fact("employees", "self_reported", "120", "inside_range"),
            Fact("business_need", "verified", "dispatch", "present"),
            Fact("agreed_next_step", "verified", "proposal", "present"),
            Fact("persona", "self_reported", "Head of Operations", "present"),
        ],
        consent_email=True,
        opt_out=False,
        email="size@parcel-032.example",
        company_name="Parcel Co",
        source="public_form",
        notes="Hello from operations.",
        meeting_requested=False,
        rules=DEFAULT_SALES_RULES,
        has_account=True,
    )
    assert decision["sales_qualified"] is False
    assert decision["not_a_fit"] is False
    assert DEFAULT_SALES_RULES["accept_self_reported_size"] is False


def test_industry_and_persona_do_not_sales_qualify() -> None:
    decision = decide_assessment(
        facts=[
            Fact("industry", "self_reported", "logistics", "match"),
            Fact("persona", "self_reported", "COO", "present"),
            Fact("business_need", "unknown"),
        ],
        consent_email=True,
        opt_out=False,
        email="hello@parcel-032.example",
        company_name="Parcel Co",
        source="public_form",
        notes="Hello.",
        meeting_requested=False,
        rules=DEFAULT_SALES_RULES,
        has_account=True,
    )
    assert decision["response_eligible"] is True
    assert decision["sales_qualified"] is False


def test_discovered_lead_with_a_grant_is_not_response_eligible(client: TestClient) -> None:
    headers = login(client)
    db = get_session()
    try:
        user = _user(db)
        lead = Lead(
            tenant_id=user.tenant_id,
            created_by=user.id,
            first_name="Found",
            last_name="Outside",
            email=f"found.{uuid4().hex[:8]}@parcel-032.example",
            consent_email=False,
            source="ai_discovery",
            notes="",
        )
        db.add(lead)
        db.add(
            AuthorizationGrant(
                tenant_id=user.tenant_id,
                created_by=user.id,
                name="Email grant does not create consent",
                mode="bounded_autopilot",
                channel="email",
                status="active",
            )
        )
        db.commit()
        lead_id = str(lead.id)
    finally:
        db.close()
    body = client.get(f"/api/v1/leads/{lead_id}/assessment", headers=headers).json()["data"]
    assert body["response_eligible"] is False
    assert body["meeting_eligible"] is False
    assert body["sales_qualified"] is False


def test_sales_qualification_handoff_is_idempotent_and_waits_without_an_account(client: TestClient) -> None:
    headers = login(client)
    account = client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": f"Parcel Verified {uuid4().hex[:6]}", "domain": f"{uuid4().hex[:8]}.example"},
    )
    assert account.status_code == 200, account.text
    account_id = account.json()["data"]["id"]
    created = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "first_name": "Ready",
            "last_name": "Buyer",
            "email": f"ready.{uuid4().hex[:8]}@parcel-032.example",
            "company_name": "Parcel Verified",
            "account_id": account_id,
            "consent_email": True,
            "notes": "We agreed to review a proposal.",
        },
    )
    assert created.status_code == 200, created.text
    lead_id = created.json()["data"]["id"]
    first = client.post(
        f"/api/v1/leads/{lead_id}/sales-qualification",
        headers=headers,
        json={"facts": _verified_facts()},
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["sales_qualified"] is True
    opportunity_id = first.json()["data"]["opportunity_id"]
    assert opportunity_id
    second = client.post(
        f"/api/v1/leads/{lead_id}/sales-qualification",
        headers=headers,
        json={"facts": _verified_facts()},
    )
    assert second.json()["data"]["opportunity_id"] == opportunity_id
    refused = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "first_name": "No",
            "last_name": "Company",
            "email": f"nocompany.{uuid4().hex[:8]}@parcel-032.example",
            "consent_email": True,
            "notes": "Need is confirmed.",
        },
    )
    assert refused.status_code == 200, refused.text
    bare_id = refused.json()["data"]["id"]
    db = get_session()
    try:
        before = db.scalar(select(func.count()).select_from(Account))
    finally:
        db.close()
    waiting = client.post(
        f"/api/v1/leads/{bare_id}/sales-qualification",
        headers=headers,
        json={"facts": _verified_facts()},
    )
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["data"]["sales_qualified"] is True
    assert waiting.json()["data"]["opportunity_id"] is None
    assert waiting.json()["data"]["next_action"] == "handoff_waiting"
    db = get_session()
    try:
        task = db.scalar(select(Task).where(Task.entity_id == bare_id, Task.title == "Resolve the account before sales handoff"))
        assert task is not None
        assert task.status == "open"
    finally:
        db.close()
    db = get_session()
    try:
        after = db.scalar(select(func.count()).select_from(Account))
        assert after == before
    finally:
        db.close()


def test_capture_commits_the_lead_and_outbox_together(client: TestClient) -> None:
    db = get_session()
    try:
        user = _user(db)
        before = db.scalar(select(func.count()).select_from(Lead).where(Lead.tenant_id == user.tenant_id))
        email = f"rollback.{uuid4().hex[:8]}@parcel-032.example"
        capture_inbound(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            payload={
                "first_name": "Roll",
                "last_name": "Back",
                "email": email,
                "company_name": "Rollback Parcel",
                "consent_email": True,
                "request_note": "Please reply.",
            },
        )
        db.rollback()
        after = db.scalar(select(func.count()).select_from(Lead).where(Lead.email == email))
        assert after == 0
        assert before is not None
    finally:
        db.close()
    db = get_session()
    try:
        user = _user(db)
        _row, token = create_form_key(db, tenant_id=user.tenant_id, actor_id=user.id, name=f"atomic-{uuid4().hex[:6]}")
        db.commit()
    finally:
        db.close()
    email = f"atomic.{uuid4().hex[:8]}@parcel-032.example"
    accepted = client.post(
        f"/api/v1/public/forms/{token}/capture",
        json={
            "first_name": "Atomic",
            "last_name": "Capture",
            "email": email,
            "company_name": "Atomic Parcel",
            "consent_email": True,
            "request_note": "We need a reply.",
            "phone": "5550100",
        },
    )
    assert accepted.status_code == 200, accepted.text
    lead_id = accepted.json()["data"]["lead"]["id"]
    db = get_session()
    try:
        lead = db.get(Lead, UUID(lead_id))
        assert lead is not None
        events = db.scalars(
            select(DomainEvent).where(DomainEvent.entity_id == lead_id, DomainEvent.event_type.in_(["lead.created", "enquiry.received"]))
        ).all()
        assert {row.event_type for row in events} == {"lead.created", "enquiry.received"}
        assert all(row.delivery_status == "pending" and row.processed_at is None for row in events)
        account = db.get(Account, lead.account_id)
        assert account is not None
        assert account.industry == ""
        assert account.employee_count is None
        contact = db.get(Contact, lead.contact_id)
        assert contact is not None
        assert contact.phone == "5550100"
        assert contact.opt_out is False
    finally:
        db.close()


def test_repeat_capture_updates_the_contact_and_keeps_opt_out(client: TestClient) -> None:
    headers = login(client)
    email = f"repeat.{uuid4().hex[:8]}@parcel-032.example"
    company = f"Repeat Parcel {uuid4().hex[:6]}"
    first = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={
            "first_name": "Repeat",
            "last_name": "Person",
            "email": email,
            "company_name": company,
            "consent_email": True,
            "phone": "5551000",
            "request_note": "First note",
        },
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={
            "first_name": "Repeat",
            "last_name": "Person",
            "email": email,
            "company_name": company,
            "consent_email": True,
            "phone": "5552000",
            "request_note": "Second note",
        },
    )
    assert second.status_code == 200, second.text
    db = get_session()
    try:
        contacts = db.scalars(select(Contact).where(Contact.email == email)).all()
        assert len(contacts) == 1
        assert contacts[0].phone == "5552000"
        contacts[0].opt_out = True
        db.commit()
        tenant_id = contacts[0].tenant_id
    finally:
        db.close()
    blocked = client.post(
        "/api/v1/acquisition/capture",
        headers=headers,
        json={"first_name": "Repeat", "last_name": "Person", "email": email, "company_name": company, "consent_email": True},
    )
    assert blocked.status_code == 409
    db = get_session()
    try:
        contact = db.scalar(select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email))
        assert contact is not None
        assert contact.opt_out is True
        assert contact.phone == "5552000"
    finally:
        db.close()


def test_running_effect_is_visible_and_recovery_does_not_call_twice(client: TestClient) -> None:
    _ = client
    db = get_session()
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        step = db.scalar(select(AutonomousRunStep).where(AutonomousRunStep.run_id == run.id, AutonomousRunStep.status == "running"))
        assert step is not None
        assert step.started_at is not None
        assert step.finished_at is None
        assert step.lease_until is not None
        raise TimeoutError("provider accepted then timed out")

    def reconcile(_row: ExternalEffect) -> ReconciledEffect:
        return ReconciledEffect("confirmed", "provider-1")

    try:
        user = _user(db)
        run = AutonomousRun(tenant_id=user.tenant_id, created_by=user.id, status="running", workflow="effect_test", trigger="manual")
        db.add(run)
        db.flush()
        first = execute_external_effect(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            run=run,
            action="email.send",
            channel="email",
            target_id="person-1",
            content_version="v1",
            grant_id="grant-1",
            call=call,
            reconcile=reconcile,
        )
        assert first.outcome == "unknown"
        assert calls["n"] == 1
        run.status = "cancelled"
        run.cancelled_at = datetime.now(UTC)
        second = execute_external_effect(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            run=run,
            action="email.send",
            channel="email",
            target_id="person-1",
            content_version="v1",
            grant_id="grant-1",
            call=call,
            reconcile=reconcile,
        )
        assert calls["n"] == 1
        assert second.outcome == "confirmed"
        assert second.provider_ref == "provider-1"
        db.rollback()
    finally:
        db.close()


def test_confirmed_failure_is_not_retried(client: TestClient) -> None:
    _ = client
    db = get_session()
    calls = {"n": 0}

    def call() -> EffectAttempt:
        calls["n"] += 1
        return EffectAttempt(failed=True, retryable=False)

    def reconcile(_row: ExternalEffect) -> ReconciledEffect:
        raise AssertionError("confirmed failure must not be reconciled as unknown")

    try:
        user = _user(db)
        run = AutonomousRun(tenant_id=user.tenant_id, created_by=user.id, status="running", workflow="effect_fail", trigger="manual")
        db.add(run)
        db.flush()
        kwargs = {
            "tenant_id": user.tenant_id,
            "actor_id": user.id,
            "run": run,
            "action": "email.send",
            "channel": "email",
            "target_id": "person-2",
            "content_version": "v1",
            "grant_id": "grant-1",
            "call": call,
            "reconcile": reconcile,
        }
        first = execute_external_effect(db, **kwargs)
        assert first.outcome == "confirmed_failure"
        second = execute_external_effect(db, **kwargs)
        assert second.id == first.id
        assert calls["n"] == 1
        kwargs["content_version"] = "v2"
        execute_external_effect(db, **kwargs)
        assert calls["n"] == 2
        db.rollback()
    finally:
        db.close()


def test_pause_can_resume_and_cancel_cannot(client: TestClient) -> None:
    headers = login(client)
    db = get_session()
    try:
        user = _user(db)
        run = AutonomousRun(tenant_id=user.tenant_id, created_by=user.id, status="running", workflow="journey_control", trigger="manual")
        db.add(run)
        db.commit()
        run_id = str(run.id)
    finally:
        db.close()
    paused = client.post(f"/api/v1/journeys/{run_id}/pause", headers={**headers, "Idempotency-Key": "pause-once"})
    assert paused.status_code == 200, paused.text
    assert paused.json()["data"]["status"] == "paused"
    job_id = paused.json()["data"]["job_id"]
    again = client.post(f"/api/v1/journeys/{run_id}/pause", headers={**headers, "Idempotency-Key": "pause-once"})
    assert again.status_code == 200, again.text
    assert again.json()["data"]["job_id"] == job_id
    resumed = client.post(f"/api/v1/journeys/{run_id}/resume", headers={**headers, "Idempotency-Key": "resume-once"})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["data"]["status"] == "running"
    cancelled = client.post(f"/api/v1/journeys/{run_id}/cancel", headers={**headers, "Idempotency-Key": "cancel-once"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "cancelled"
    denied = client.post(f"/api/v1/journeys/{run_id}/resume", headers={**headers, "Idempotency-Key": "resume-after-cancel"})
    assert denied.status_code == 409
    db = get_session()
    try:
        stored = db.get(AutonomousRun, UUID(run_id))
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.paused_at is None or stored.cancelled_at is not None
        assert stored.cancelled_at is not None
    finally:
        db.close()


def test_learning_window_uses_deal_won_and_censors_open_outcomes(client: TestClient) -> None:
    _ = client
    spec = TASKS["LEAD_CONVERSION"]
    assert spec["horizon"] == 90
    assert spec["observation_window_days"] == 90
    assert "deal.won" in spec["positive"]
    assert "lead.qualified" in spec["label"]
    db = get_session()
    try:
        user = _user(db)
        account = Account(tenant_id=user.tenant_id, created_by=user.id, name="Label Parcel", domain=f"{uuid4().hex[:8]}.example")
        db.add(account)
        db.flush()
        lead = Lead(
            tenant_id=user.tenant_id,
            created_by=user.id,
            account_id=account.id,
            first_name="Label",
            last_name="Lead",
            email=f"label.{uuid4().hex[:8]}@parcel-032.example",
            company_name="Label Parcel",
            consent_email=True,
        )
        opportunity = Opportunity(
            tenant_id=user.tenant_id,
            created_by=user.id,
            account_id=account.id,
            name="Label deal",
            stage="qualification",
        )
        db.add(lead)
        db.add(opportunity)
        db.flush()
        journey_key = f"lead:{lead.id}"
        db.add(JourneyLink(tenant_id=user.tenant_id, created_by=user.id, journey_key=journey_key, entity_type="lead", entity_id=str(lead.id), role="source"))
        db.add(
            JourneyLink(
                tenant_id=user.tenant_id,
                created_by=user.id,
                journey_key=journey_key,
                entity_type="opportunity",
                entity_id=str(opportunity.id),
                role="sales_handoff",
            )
        )
        as_of = datetime.now(UTC) - timedelta(days=30)
        db.add(
            DomainEvent(
                tenant_id=user.tenant_id,
                event_type="lead.qualified",
                entity_type="lead",
                entity_id=str(lead.id),
                created_at=as_of + timedelta(days=1),
            )
        )
        qualified_only = resolve_label(
            db,
            tenant_id=user.tenant_id,
            task_key="LEAD_CONVERSION",
            entity_type="lead",
            entity_id=str(lead.id),
            as_of=as_of,
        )
        assert qualified_only.status == "PENDING"
        assert qualified_only.value is None
        db.add(
            DomainEvent(
                tenant_id=user.tenant_id,
                event_type="deal.won",
                entity_type="opportunity",
                entity_id=str(opportunity.id),
                created_at=as_of + timedelta(days=2),
            )
        )
        db.flush()
        won = resolve_label(
            db,
            tenant_id=user.tenant_id,
            task_key="LEAD_CONVERSION",
            entity_type="lead",
            entity_id=str(lead.id),
            as_of=as_of,
        )
        assert won.status == "POSITIVE"
        assert won.value == 1
        open_lead = Lead(
            tenant_id=user.tenant_id,
            created_by=user.id,
            first_name="Open",
            last_name="Lead",
            email=f"open.{uuid4().hex[:8]}@parcel-032.example",
            consent_email=True,
        )
        db.add(open_lead)
        db.flush()
        censored = resolve_label(
            db,
            tenant_id=user.tenant_id,
            task_key="LEAD_CONVERSION",
            entity_type="lead",
            entity_id=str(open_lead.id),
            as_of=datetime(2020, 1, 1, tzinfo=UTC),
            now=datetime(2021, 6, 1, tzinfo=UTC),
        )
        assert censored.status == "CENSORED"
        assert censored.value is None
        lost = Opportunity(
            tenant_id=user.tenant_id,
            created_by=user.id,
            account_id=account.id,
            name="Lost deal",
            stage="closed_lost",
        )
        lost_lead = Lead(
            tenant_id=user.tenant_id,
            created_by=user.id,
            account_id=account.id,
            first_name="Lost",
            last_name="Lead",
            email=f"lost.{uuid4().hex[:8]}@parcel-032.example",
            consent_email=True,
        )
        db.add(lost)
        db.add(lost_lead)
        db.flush()
        lost_key = f"lead:{lost_lead.id}"
        db.add(JourneyLink(tenant_id=user.tenant_id, created_by=user.id, journey_key=lost_key, entity_type="lead", entity_id=str(lost_lead.id), role="source"))
        db.add(
            JourneyLink(
                tenant_id=user.tenant_id,
                created_by=user.id,
                journey_key=lost_key,
                entity_type="opportunity",
                entity_id=str(lost.id),
                role="sales_handoff",
            )
        )
        db.add(
            DomainEvent(
                tenant_id=user.tenant_id,
                event_type="deal.lost",
                entity_type="opportunity",
                entity_id=str(lost.id),
                created_at=as_of + timedelta(days=3),
            )
        )
        db.flush()
        negative = resolve_label(
            db,
            tenant_id=user.tenant_id,
            task_key="LEAD_CONVERSION",
            entity_type="lead",
            entity_id=str(lost_lead.id),
            as_of=as_of,
        )
        assert negative.status == "NEGATIVE"
        assert negative.value == 0
        db.rollback()
    finally:
        db.close()


def test_unknown_model_fails_closed_and_mock_stays_mock(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    get_settings.cache_clear()
    try:
        llama = get_llm_provider()
        assert isinstance(llama, NotConfiguredLLMProvider)
        text = llama.complete("hello", system="test").text
        assert "not implemented" in text.lower()
        assert "MOCK LLM" not in text
        monkeypatch.setenv("LLM_PROVIDER", "kimi")
        get_settings.cache_clear()
        kimi = get_llm_provider()
        assert isinstance(kimi, NotConfiguredLLMProvider)
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        get_settings.cache_clear()
        assert isinstance(get_llm_provider(), MockLLMProvider)
    finally:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        get_settings.cache_clear()


def test_sandbox_activation_does_not_call_meta(monkeypatch) -> None:
    class ExplodingClient:
        def post(self, *_args, **_kwargs):
            raise AssertionError("sandbox activate must not call Meta")

        def close(self) -> None:
            return None

    provider = MetaAdsProvider(token="test-token", ad_account_id="123", client=ExplodingClient(), sandbox=True)  # type: ignore[arg-type]
    result = provider.activate_campaign(external_id="campaign-1")
    assert result.ok is False
    assert result.failure_class == "CONFIGURATION"
    assert "spend" in result.reason.lower()
    monkeypatch.setenv("META_ADS_MODE", "sandbox")
    monkeypatch.setenv("META_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123")
    get_settings.cache_clear()
    try:
        resolved = get_ads_provider("meta")
        assert isinstance(resolved, MetaAdsProvider)
        assert resolved._sandbox is True
    finally:
        monkeypatch.delenv("META_ADS_MODE", raising=False)
        monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("META_AD_ACCOUNT_ID", raising=False)
        get_settings.cache_clear()
