from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.providers import GeminiEmbeddingProvider, GeminiLLMProvider, NotConfiguredLLMProvider, get_llm_provider
from app.core.config import get_settings
from app.db.session import get_session
from app.models.identity import User
from app.models.integrations import ProviderAccount, WebhookRoute
from app.providers.ads import LinkedInAdsProvider, MockAdsProvider, NotConfiguredAdsProvider, get_ads_provider
from app.providers.lead_discovery import (
    ApifyLeadDiscoveryProvider,
    MockLeadDiscoveryProvider,
    NotConfiguredDiscoveryProvider,
    get_lead_discovery_provider,
)
from app.providers.voice_telephony import TwilioTelephonyProvider
from app.services.pilot_readiness import activate_mode
from app.services.provider_accounts import upsert_token_account
from app.services.provider_provision import channel_modes
from app.services.provider_resolve import resolve_channel
from app.services.voice_router import compose_voice_provider
from app.services.webhook_routes import demo_routing_token, ensure_route, hash_routing_token
from tests.conftest import login


def _tenant(db):
    user = db.scalar(select(User).where(User.email == "admin@agrayian.demo"))
    assert user is not None
    return user


def test_tenant_row_makes_ads_and_discovery_live_when_env_is_mock(client: TestClient, monkeypatch) -> None:
    login(client)
    monkeypatch.setenv("LINKEDIN_ADS_MODE", "mock")
    monkeypatch.setenv("DISCOVERY_PROVIDER", "mock")
    get_settings.cache_clear()
    db = get_session()
    try:
        user = _tenant(db)
        upsert_token_account(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            provider="linkedin",
            access_token="tenant-linkedin-token",
            extra={"account_id": "acct-1"},
        )
        upsert_token_account(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            provider="apify",
            access_token="tenant-apify-token",
            extra={"actor_id": "harvestapi/linkedin-profile-search"},
        )
        db.commit()
        ads = get_ads_provider("linkedin", db, user.tenant_id)
        discovery = get_lead_discovery_provider(db, user.tenant_id)
        linkedin = resolve_channel(db, user.tenant_id, "linkedin")
        found = resolve_channel(db, user.tenant_id, "discovery")
        assert isinstance(ads, LinkedInAdsProvider)
        assert ads.health().is_mock is False
        assert ads.health().connected is True
        assert linkedin.mode == "LIVE"
        assert linkedin.reason == "tenant credential"
        assert isinstance(discovery, ApifyLeadDiscoveryProvider)
        assert discovery.health()["is_mock"] is False
        assert discovery.health()["connected"] is True
        assert found.mode == "LIVE"
        health = client.get("/api/v1/integrations/providers", headers=login(client)).json()["data"]
        ads_row = next(row for row in health if row["name"] == "LinkedIn Ads")
        assert ads_row["mode"] == "LIVE"
        for row in db.scalars(select(ProviderAccount).where(ProviderAccount.tenant_id == user.tenant_id, ProviderAccount.provider.in_(["linkedin", "apify"]))).all():
            row.status = "disconnected"
        db.commit()
    finally:
        db.close()
        monkeypatch.delenv("LINKEDIN_ADS_MODE", raising=False)
        monkeypatch.delenv("DISCOVERY_PROVIDER", raising=False)
        get_settings.cache_clear()


def test_live_without_creds_is_not_silent_mock(monkeypatch) -> None:
    monkeypatch.setenv("LINKEDIN_ADS_MODE", "live")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "")
    monkeypatch.setenv("LINKEDIN_AD_ACCOUNT_ID", "")
    monkeypatch.setenv("DISCOVERY_PROVIDER", "apify")
    monkeypatch.setenv("APIFY_API_TOKEN", "")
    monkeypatch.setenv("APIFY_ACTOR_ID", "")
    get_settings.cache_clear()
    try:
        ads = get_ads_provider("linkedin")
        discovery = get_lead_discovery_provider()
        assert isinstance(ads, NotConfiguredAdsProvider)
        assert not isinstance(ads, MockAdsProvider) or ads.health().is_mock is False
        assert ads.health().is_mock is False
        assert isinstance(discovery, NotConfiguredDiscoveryProvider)
        assert not isinstance(discovery, MockLeadDiscoveryProvider)
        assert discovery.health()["is_mock"] is False
    finally:
        monkeypatch.delenv("LINKEDIN_ADS_MODE", raising=False)
        monkeypatch.delenv("DISCOVERY_PROVIDER", raising=False)
        get_settings.cache_clear()


def test_tenant_row_makes_voice_live_when_env_is_mock(client: TestClient, monkeypatch) -> None:
    login(client)
    monkeypatch.setenv("VOICE_PROVIDER", "mock")
    get_settings.cache_clear()
    db = get_session()
    try:
        user = _tenant(db)
        upsert_token_account(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            provider="twilio",
            access_token="tenant-twilio-token",
            extra={"account_sid": "ACtenant", "from_number": "+15550001111", "twiml_url": "https://example.test/twiml"},
        )
        upsert_token_account(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            provider="vapi",
            access_token="tenant-vapi-token",
            extra={"assistant_id": "asst-1", "phone_number_id": "pn-1"},
        )
        db.commit()
        provider = compose_voice_provider(db, user.tenant_id, "+15551230000")
        health = provider.health()
        assert isinstance(provider.telephony, TwilioTelephonyProvider)
        assert health.is_mock is False
        assert health.connected is True
        assert resolve_channel(db, user.tenant_id, "twilio").reason == "tenant credential"
    finally:
        for row in db.scalars(select(ProviderAccount).where(ProviderAccount.tenant_id == user.tenant_id, ProviderAccount.provider.in_(["twilio", "vapi"]))).all():
            row.status = "disconnected"
        db.commit()
        db.close()
        monkeypatch.delenv("VOICE_PROVIDER", raising=False)
        get_settings.cache_clear()


def test_gemini_chat_posts_generate_content(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_REASONING_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "modelVersion": "gemini-2.5-flash",
                "candidates": [{"content": {"parts": [{"text": "draft"}, {"thought": True, "text": "hidden"}]}}],
                "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
            }

    class _Client:
        def __init__(self) -> None:
            self.url = ""
            self.body: dict | None = None
            self.headers: dict | None = None

        def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> _Response:
            self.url = url
            self.body = json
            self.headers = headers
            return _Response()

    client = _Client()
    try:
        result = GeminiLLMProvider(api_key="test-key", client=client).complete("hello", system="write")  # type: ignore[arg-type]
        assert client.url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        assert client.headers is not None
        assert client.headers["x-goog-api-key"] == "test-key"
        assert client.body is not None
        assert client.body["systemInstruction"] == {"parts": [{"text": "write"}]}
        assert client.body["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
        assert "generationConfig" not in client.body
        assert result.provider == "gemini"
        assert result.text == "draft"
        assert result.is_mock is False
        assert result.input_tokens == 3
        reasoned = GeminiLLMProvider(api_key="test-key", client=client).complete("why", system="analyze", reasoning=True)  # type: ignore[arg-type]
        assert client.body is not None
        assert client.body["generationConfig"] == {"thinkingConfig": {"thinkingBudget": 2048}}
        assert reasoned.provider == "gemini"
    finally:
        monkeypatch.delenv("GEMINI_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("GEMINI_REASONING_MODEL", raising=False)
        get_settings.cache_clear()


def test_gemini_embeddings_post_batch_embed(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    get_settings.cache_clear()

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"embeddings": [{"values": [0.1, 0.2]}, {"values": [0.3, 0.4]}]}

    class _Client:
        def __init__(self) -> None:
            self.url = ""
            self.body: dict | None = None

        def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> _Response:
            self.url = url
            self.body = json
            return _Response()

    client = _Client()
    try:
        vectors = GeminiEmbeddingProvider(api_key="test-key", client=client).embed(["one", "two"])  # type: ignore[arg-type]
        assert client.url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
        assert client.body is not None
        assert client.body["requests"][0]["model"] == "models/gemini-embedding-001"
        assert client.body["requests"][0]["taskType"] == "SEMANTIC_SIMILARITY"
        assert client.body["requests"][1]["content"] == {"parts": [{"text": "two"}]}
        assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    finally:
        monkeypatch.delenv("GEMINI_EMBEDDING_MODEL", raising=False)
        get_settings.cache_clear()


def test_gemini_live_without_key_is_not_silent_mock(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        llm = get_llm_provider()
        assert isinstance(llm, NotConfiguredLLMProvider)
        result = llm.complete("hello", system="test")
        assert result.is_mock is False
        assert "NOT_CONFIGURED" in result.text
    finally:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        get_settings.cache_clear()


def test_activate_provisions_tenant_credentials_from_env(client: TestClient, monkeypatch) -> None:
    login(client)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-activate")
    monkeypatch.setenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("DISCOVERY_PROVIDER", "apify")
    monkeypatch.setenv("APIFY_API_TOKEN", "apify-test-activate")
    monkeypatch.setenv("APIFY_ACTOR_ID", "harvestapi/linkedin-profile-search")
    get_settings.cache_clear()
    db = get_session()
    try:
        user = _tenant(db)
        activate_mode(db, tenant_id=user.tenant_id, actor_id=user.id, target="DEMO", reason="full-funnel activate")
        db.commit()
        modes = channel_modes(db, user.tenant_id)
        assert modes["gemini"]["mode"] == "LIVE"
        assert modes["gemini"]["tenant_credential"] is True
        assert modes["discovery"]["mode"] == "LIVE"
        assert modes["discovery"]["tenant_credential"] is True
        assert isinstance(get_llm_provider(db, user.tenant_id), GeminiLLMProvider)
        assert isinstance(get_lead_discovery_provider(db, user.tenant_id), ApifyLeadDiscoveryProvider)
    finally:
        for row in db.scalars(select(ProviderAccount).where(ProviderAccount.tenant_id == user.tenant_id, ProviderAccount.provider.in_(["gemini", "apify"]))).all():
            row.status = "disconnected"
        db.commit()
        db.close()
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("DISCOVERY_PROVIDER", raising=False)
        monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
        monkeypatch.delenv("APIFY_ACTOR_ID", raising=False)
        get_settings.cache_clear()


def test_ensure_route_does_not_rotate_existing_token(client: TestClient) -> None:
    login(client)
    db = get_session()
    try:
        user = _tenant(db)
        original = demo_routing_token("agrayian", "twilio")
        first = ensure_route(db, tenant_id=user.tenant_id, provider="twilio", raw_token=original)
        second = ensure_route(db, tenant_id=user.tenant_id, provider="twilio")
        row = db.scalar(
            select(WebhookRoute).where(
                WebhookRoute.tenant_id == user.tenant_id,
                WebhookRoute.provider == "twilio",
                WebhookRoute.deleted_at.is_(None),
            )
        )
        assert first == original
        assert second == ""
        assert row is not None
        assert row.token_hash == hash_routing_token(original)
    finally:
        db.close()


def test_undecryptable_tenant_credential_does_not_500_providers(client: TestClient) -> None:
    headers = login(client)
    db = get_session()
    try:
        user = _tenant(db)
        upsert_token_account(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            provider="gemini",
            access_token="temporary-key",
        )
        db.commit()
        row = db.scalar(
            select(ProviderAccount).where(
                ProviderAccount.tenant_id == user.tenant_id,
                ProviderAccount.provider == "gemini",
                ProviderAccount.deleted_at.is_(None),
            )
        )
        assert row is not None
        row.access_token_encrypted = "v1:not-a-valid-fernet-token"
        db.commit()
        resolved = resolve_channel(db, user.tenant_id, "gemini")
        assert resolved.mode == "NOT_CONFIGURED"
        assert "decrypt" in resolved.reason.lower()
        response = client.get("/api/v1/integrations/providers", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]
        row.status = "disconnected"
        db.commit()
    finally:
        db.close()
