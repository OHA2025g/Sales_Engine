from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session
from app.models.lifecycle import Campaign
from app.providers.ads import AdsCampaignResult, AdsHealth, AdsMetrics, AdsSpend, MetaAdsProvider, MockAdsProvider
from app.services.ads import EXHAUSTED_DAILY, NO_SPEND, budget_block_reason, derived_metrics, sync_campaign
from tests.conftest import login


def _allow_spend(client: TestClient, headers: dict, daily: str = "100000", monthly: str = "100000") -> None:
    response = client.patch(
        "/api/v1/autonomy/settings",
        headers=headers,
        json={"daily_budget_limit": daily, "monthly_budget_limit": monthly},
    )
    assert response.status_code == 200, response.text


def _clear_spend(client: TestClient, headers: dict) -> None:
    client.patch(
        "/api/v1/autonomy/settings",
        headers=headers,
        json={"daily_budget_limit": 0, "monthly_budget_limit": 0},
    )


def test_launch_queues_approval_and_mock_does_not_invent_spend(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ads.get_ads_provider",
        lambda channel, *args, **kwargs: MockAdsProvider(channel or "linkedin"),
    )
    headers = login(client)
    _allow_spend(client, headers)
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "LinkedIn hunt", "channel": "linkedin", "objective": "pipeline", "budget": "2500"},
    )
    assert created.status_code == 200
    campaign_id = created.json()["data"]["id"]
    assert created.json()["data"]["spent"] in {"0", "0.00", 0}
    launch = client.post(f"/api/v1/lifecycle/campaigns/{campaign_id}/launch", headers=headers)
    assert launch.status_code == 200, launch.text
    approval_id = launch.json()["data"]["approval_id"]
    decided = client.post(
        f"/api/v1/ai/approvals/{approval_id}/decide",
        headers=headers,
        json={"decision": "approve", "note": "Try launch"},
    )
    assert decided.status_code == 200
    note = decided.json()["data"]["decision_note"]
    assert "invented" in note.lower() or "not launched" in note.lower() or "no live" in note.lower()
    detail = client.get(f"/api/v1/lifecycle/campaigns/{campaign_id}", headers=headers).json()["data"]
    assert detail["status"] != "launched"
    assert Decimal(str(detail["spent"])) == Decimal("0")
    _clear_spend(client, headers)


class LiveAdsStub:
    def __init__(self) -> None:
        self.launches = 0

    def health(self) -> AdsHealth:
        return AdsHealth(provider="linkedin-ads", is_mock=False, connected=True, reason="stub")

    def create_campaign(self, *, name: str, objective: str, budget: Decimal) -> AdsCampaignResult:
        self.launches += 1
        return AdsCampaignResult(ok=True, provider="linkedin-ads", is_mock=False, external_id="urn:li:sponsoredCampaign:99", provider_status="ACTIVE")

    def pause_campaign(self, *, external_id: str) -> AdsCampaignResult:
        return AdsCampaignResult(ok=True, provider="linkedin-ads", is_mock=False, external_id=external_id, provider_status="PAUSED")

    def get_status(self, *, external_id: str) -> AdsCampaignResult:
        return AdsCampaignResult(ok=True, provider="linkedin-ads", is_mock=False, external_id=external_id, provider_status="ACTIVE")

    def get_spend(self, *, external_id: str) -> AdsSpend:
        return AdsSpend(amount=Decimal("12.50"), currency="USD", provider="linkedin-ads", is_mock=False, reason="")

    def get_metrics(self, *, external_id: str) -> AdsMetrics:
        return AdsMetrics(
            spend=Decimal("12.50"),
            impressions=1000,
            clicks=25,
            conversions=2,
            currency="USD",
            provider="linkedin-ads",
            is_mock=False,
            provider_status="ACTIVE",
        )


def test_budget_exceeded_blocks_launch(client: TestClient) -> None:
    headers = login(client)
    _allow_spend(client, headers, daily="100", monthly="1000")
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Over budget", "channel": "linkedin", "budget": "250"},
    )
    launch = client.post(f"/api/v1/lifecycle/campaigns/{created.json()['data']['id']}/launch", headers=headers)
    assert launch.status_code == 409
    assert "exceeded" in launch.text
    _clear_spend(client, headers)


def test_successful_launch_and_idempotent_retry(client: TestClient, monkeypatch) -> None:
    stub = LiveAdsStub()
    monkeypatch.setattr("app.services.ads.get_ads_provider", lambda channel, *args, **kwargs: stub)
    headers = login(client)
    _allow_spend(client, headers)
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Live hunt", "channel": "linkedin", "objective": "pipeline", "budget": "500"},
    )
    campaign_id = created.json()["data"]["id"]
    launch = client.post(f"/api/v1/lifecycle/campaigns/{campaign_id}/launch", headers=headers)
    assert launch.status_code == 200, launch.text
    approval_id = launch.json()["data"]["approval_id"]
    first = client.post(f"/api/v1/ai/approvals/{approval_id}/decide", headers=headers, json={"decision": "approve", "note": "go"})
    assert first.status_code == 200
    second = client.post(f"/api/v1/ai/approvals/{approval_id}/decide", headers=headers, json={"decision": "approve", "note": "again"})
    assert second.status_code == 200
    assert stub.launches == 1
    detail = client.get(f"/api/v1/lifecycle/campaigns/{campaign_id}", headers=headers).json()["data"]
    assert detail["status"] == "launched"
    assert detail["external_campaign_id"] == "urn:li:sponsoredCampaign:99"
    _clear_spend(client, headers)


def test_provider_error_does_not_mark_launched(client: TestClient, monkeypatch) -> None:
    class BrokenAds(LiveAdsStub):
        def create_campaign(self, *, name: str, objective: str, budget: Decimal) -> AdsCampaignResult:
            return AdsCampaignResult(ok=False, provider="linkedin-ads", is_mock=False, reason="LinkedIn refused", failure_class="PERMANENT")

    monkeypatch.setattr("app.services.ads.get_ads_provider", lambda channel, *args, **kwargs: BrokenAds())
    headers = login(client)
    _allow_spend(client, headers)
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Broken", "channel": "linkedin", "budget": "200"},
    )
    campaign_id = created.json()["data"]["id"]
    launch = client.post(f"/api/v1/lifecycle/campaigns/{campaign_id}/launch", headers=headers)
    client.post(f"/api/v1/ai/approvals/{launch.json()['data']['approval_id']}/decide", headers=headers, json={"decision": "approve", "note": "try"})
    detail = client.get(f"/api/v1/lifecycle/campaigns/{campaign_id}", headers=headers).json()["data"]
    assert detail["status"] != "launched"
    assert not detail["external_campaign_id"]
    _clear_spend(client, headers)


def test_metric_normalization_requires_inputs() -> None:
    partial = AdsMetrics(spend=Decimal("10"), impressions=None, clicks=None, conversions=None, currency="USD", provider="linkedin-ads", is_mock=False)
    derived = derived_metrics(partial)
    assert derived["ctr"] is None
    assert derived["cpc"] is None
    full = AdsMetrics(spend=Decimal("10"), impressions=100, clicks=10, conversions=2, currency="USD", provider="linkedin-ads", is_mock=False)
    ready = derived_metrics(full)
    assert ready["ctr"] == Decimal("0.1")
    assert ready["cpc"] == Decimal("1")


def test_status_sync_uses_provider_metrics(client: TestClient, monkeypatch) -> None:
    stub = LiveAdsStub()
    monkeypatch.setattr("app.services.ads.get_ads_provider", lambda channel, *args, **kwargs: stub)
    headers = login(client)
    _allow_spend(client, headers)
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Sync me", "channel": "linkedin", "budget": "200"},
    )
    campaign_id = created.json()["data"]["id"]
    launch = client.post(f"/api/v1/lifecycle/campaigns/{campaign_id}/launch", headers=headers)
    client.post(f"/api/v1/ai/approvals/{launch.json()['data']['approval_id']}/decide", headers=headers, json={"decision": "approve", "note": "go"})
    db = get_session()
    try:
        row = db.scalar(select(Campaign).where(Campaign.id == UUID(campaign_id)))
        assert row is not None
        sync_campaign(db, tenant_id=row.tenant_id, actor_id=row.created_by, campaign=row)
        db.commit()
        assert row.impressions == 1000
        assert row.clicks == 25
        assert row.spent == Decimal("12.50")
    finally:
        db.close()
    _clear_spend(client, headers)


def test_outbound_campaign_cannot_launch(client: TestClient) -> None:
    headers = login(client)
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Outbound only", "channel": "outbound", "budget": "100"},
    )
    campaign_id = created.json()["data"]["id"]
    launch = client.post(f"/api/v1/lifecycle/campaigns/{campaign_id}/launch", headers=headers)
    assert launch.status_code == 409


def test_sandbox_does_not_send_an_activation_request(client: TestClient, monkeypatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url}")
        return httpx.Response(500, json={"error": "unreachable"})

    provider = MetaAdsProvider(
        token="sandbox-token",
        ad_account_id="123",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sandbox=True,
    )
    monkeypatch.setattr("app.services.ads.get_ads_provider", lambda channel, *args, **kwargs: provider)
    headers = login(client)
    _allow_spend(client, headers)
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Sandbox hunt", "channel": "instagram", "objective": "pipeline", "budget": "2500"},
    )
    campaign_id = created.json()["data"]["id"]
    launch = client.post(f"/api/v1/lifecycle/campaigns/{campaign_id}/launch", headers=headers)
    assert launch.status_code == 200, launch.text
    decided = client.post(
        f"/api/v1/ai/approvals/{launch.json()['data']['approval_id']}/decide",
        headers=headers,
        json={"decision": "approve", "note": "sandbox"},
    )
    assert decided.status_code == 200, decided.text
    note = decided.json()["data"]["decision_note"].lower()
    assert "sandbox" in note
    assert "no activation request" in note
    detail = client.get(f"/api/v1/lifecycle/campaigns/{campaign_id}", headers=headers).json()["data"]
    assert detail["status"] != "launched"
    assert Decimal(str(detail["spent"])) == Decimal("0")
    assert seen == []
    _clear_spend(client, headers)


def test_zero_spend_limit_cannot_activate_a_live_campaign(client: TestClient, monkeypatch) -> None:
    stub = LiveAdsStub()
    monkeypatch.setattr("app.services.ads.get_ads_provider", lambda channel, *args, **kwargs: stub)
    headers = login(client)
    _clear_spend(client, headers)
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Zero cap", "channel": "linkedin", "budget": "100"},
    )
    launch = client.post(f"/api/v1/lifecycle/campaigns/{created.json()['data']['id']}/launch", headers=headers)
    assert launch.status_code == 409
    assert NO_SPEND in launch.text
    assert stub.launches == 0
    _allow_spend(client, headers)
    queued = client.post(f"/api/v1/lifecycle/campaigns/{created.json()['data']['id']}/launch", headers=headers)
    assert queued.status_code == 200, queued.text
    _clear_spend(client, headers)
    decided = client.post(
        f"/api/v1/ai/approvals/{queued.json()['data']['approval_id']}/decide",
        headers=headers,
        json={"decision": "approve", "note": "limit removed"},
    )
    assert decided.status_code == 200
    assert stub.launches == 0
    detail = client.get(f"/api/v1/lifecycle/campaigns/{created.json()['data']['id']}", headers=headers).json()["data"]
    assert detail["status"] != "launched"


def test_missing_and_invalid_limits_do_not_authorize_spend() -> None:
    class Settings:
        tenant_id = UUID(int=1)
        daily_budget_limit = None
        monthly_budget_limit = 100

    class CampaignRow:
        budget = Decimal("10")

    assert budget_block_reason(None, settings=Settings(), campaign=CampaignRow()) == NO_SPEND  # type: ignore[arg-type]
    Settings.daily_budget_limit = "nope"
    assert budget_block_reason(None, settings=Settings(), campaign=CampaignRow()) == NO_SPEND  # type: ignore[arg-type]
    Settings.daily_budget_limit = -1
    Settings.monthly_budget_limit = 100
    assert budget_block_reason(None, settings=Settings(), campaign=CampaignRow()) == NO_SPEND  # type: ignore[arg-type]
    Settings.daily_budget_limit = 0
    assert budget_block_reason(None, settings=Settings(), campaign=CampaignRow()) == NO_SPEND  # type: ignore[arg-type]


def test_exhausted_spend_limit_cannot_activate(client: TestClient, monkeypatch) -> None:
    stub = LiveAdsStub()
    monkeypatch.setattr("app.services.ads.get_ads_provider", lambda channel, *args, **kwargs: stub)
    headers = login(client)
    _allow_spend(client, headers, daily="100", monthly="100")
    spent = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Already spent", "channel": "linkedin", "budget": "10"},
    )
    db = get_session()
    try:
        row = db.get(Campaign, UUID(spent.json()["data"]["id"]))
        assert row is not None
        row.spent = Decimal("100")
        row.last_synced_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
    created = client.post(
        "/api/v1/lifecycle/campaigns",
        headers=headers,
        json={"name": "Past the cap", "channel": "linkedin", "budget": "10"},
    )
    launch = client.post(f"/api/v1/lifecycle/campaigns/{created.json()['data']['id']}/launch", headers=headers)
    assert launch.status_code == 409
    assert EXHAUSTED_DAILY in launch.text
    assert stub.launches == 0
    _clear_spend(client, headers)
