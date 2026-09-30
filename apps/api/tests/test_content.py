from fastapi.testclient import TestClient

from app.ai.providers import CompletionResult
from app.core.config import get_settings
from app.providers.ads import AdsCampaignResult
from tests.conftest import login

STRUCTURED = """===LINKEDIN_POST===
headline: Ship the note
body: Tell the buyer what changed and how to reply.
cta: Start a conversation
===FACEBOOK_POST===
headline: Ship the note
body: A page post grounded in the product description.
cta: Send a note
===INSTAGRAM_POST===
headline: Ship the note
body: A caption grounded in the product description.
cta: Message us
===AD===
headline: Pipeline from one offer
body: A paused ad brief grounded in the product description.
cta: Request a walkthrough
"""


class _StubLLM:
    def __init__(self, text: str, *, is_mock: bool) -> None:
        self._text = text
        self._is_mock = is_mock

    def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
        _ = (prompt, system, model, reasoning)
        return CompletionResult(
            text=self._text,
            provider="stub",
            model="stub",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            is_mock=self._is_mock,
            estimated_cost=0.0,
        )


def _ready(client: TestClient, headers: dict[str, str]) -> str:
    profile = client.put(
        "/api/v1/content/profile",
        headers=headers,
        json={
            "company_name": "Northwind",
            "summary": "We help revenue teams keep one record from first touch to renewal.",
            "audience": "B2B revenue leaders",
            "website": "https://example.com",
            "proof": "",
            "capture_url": "https://example.com/capture/demo",
        },
    )
    assert profile.status_code == 200
    product = client.post(
        "/api/v1/content/products",
        headers=headers,
        json={"sku": "REV-1", "name": "Revenue OS", "description": "One workspace for pipeline, quotes, and onboarding."},
    )
    assert product.status_code == 200
    return product.json()["data"]["id"]


def test_mock_generation_does_not_publish(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.services.content.get_llm_provider", lambda *_args, **_kwargs: _StubLLM(STRUCTURED, is_mock=True))
    headers = login(client)
    product_id = _ready(client, headers)
    created = client.post("/api/v1/content/generate", headers=headers, json={"product_id": product_id, "ad_channel": "linkedin"})
    assert created.status_code == 200
    rows = created.json()["data"]
    assert len(rows) == 4
    assert {row["status"] for row in rows} == {"draft"}
    assert all(row["external_id"] == "" for row in rows)
    assert all("example.com/capture/demo" in row["destination_url"] for row in rows)
    assert all(row["is_mock"] is True for row in rows)


def test_missing_gemini_key_is_not_a_silent_draft(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.content.get_llm_provider",
        lambda *_args, **_kwargs: _StubLLM("[NOT_CONFIGURED LLM] GEMINI_API_KEY is missing.", is_mock=False),
    )
    headers = login(client)
    product_id = _ready(client, headers)
    created = client.post("/api/v1/content/generate", headers=headers, json={"product_id": product_id, "ad_channel": "linkedin"})
    assert created.status_code == 200
    rows = created.json()["data"]
    assert rows
    assert all(row["status"] == "failed" for row in rows)
    assert all("NOT_CONFIGURED" in row["error"] for row in rows)
    assert all(row["body"] == "" for row in rows)


def test_publish_post_uses_social_publisher_without_a_live_send(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("LINKEDIN_POSTING_MODE", "mock")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.content.get_llm_provider", lambda *_args, **_kwargs: _StubLLM(STRUCTURED, is_mock=True))
    headers = login(client)
    try:
        product_id = _ready(client, headers)
        created = client.post("/api/v1/content/generate", headers=headers, json={"product_id": product_id, "ad_channel": "linkedin"})
        draft = next(row for row in created.json()["data"] if row["channel"] == "linkedin" and row["kind"] == "post")
        published = client.post(f"/api/v1/content/drafts/{draft['id']}/publish", headers=headers)
        assert published.status_code == 200
        body = published.json()["data"]
        assert body["status"] == "mock"
        assert body["is_mock"] is True
        assert body["social_post_id"]
        listed = client.get("/api/v1/social/posts", headers=headers)
        assert any(item["id"] == body["social_post_id"] and item["is_mock"] is True for item in listed.json()["data"])
    finally:
        monkeypatch.delenv("LINKEDIN_POSTING_MODE", raising=False)
        get_settings.cache_clear()


def test_optional_brief_is_stored_and_sent_copy_is_remembered(client: TestClient, monkeypatch) -> None:
    seen: list[str] = []

    class _Capture:
        def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
            _ = (system, model, reasoning)
            seen.append(prompt)
            return CompletionResult(
                text=STRUCTURED,
                provider="stub",
                model="stub",
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
                is_mock=True,
                estimated_cost=0.0,
            )

    monkeypatch.setenv("LINKEDIN_POSTING_MODE", "mock")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.content.get_llm_provider", lambda *_args, **_kwargs: _Capture())
    headers = login(client)
    try:
        product_id = _ready(client, headers)
        created = client.post(
            "/api/v1/content/generate",
            headers=headers,
            json={"product_id": product_id, "ad_channel": "linkedin", "brief": "Mention the approval step"},
        )
        assert created.status_code == 200
        rows = created.json()["data"]
        assert all(row["brief"] == "Mention the approval step" for row in rows)
        assert "Mention the approval step" in seen[0]
        assert "Nothing has been sent for this product yet." in seen[0]
        draft = next(row for row in rows if row["channel"] == "linkedin" and row["kind"] == "post")
        published = client.post(f"/api/v1/content/drafts/{draft['id']}/publish", headers=headers)
        assert published.status_code == 200
        again = client.post("/api/v1/content/generate", headers=headers, json={"product_id": product_id, "ad_channel": "linkedin"})
        assert again.status_code == 200
        assert "left no note" in seen[1]
        assert "Already sent" in seen[1]
        assert "Ship the note" in seen[1]
    finally:
        monkeypatch.delenv("LINKEDIN_POSTING_MODE", raising=False)
        get_settings.cache_clear()


def test_gemini_outage_records_a_failed_draft(client: TestClient, monkeypatch) -> None:
    class _Down:
        def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
            _ = (prompt, system, model, reasoning)
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr("app.services.content.get_llm_provider", lambda *_args, **_kwargs: _Down())
    headers = login(client)
    product_id = _ready(client, headers)
    created = client.post("/api/v1/content/generate", headers=headers, json={"product_id": product_id, "ad_channel": "linkedin"})
    assert created.status_code == 200
    rows = created.json()["data"]
    assert rows
    assert all(row["status"] == "failed" for row in rows)
    assert all("Nothing was written or published" in row["error"] for row in rows)
    assert all(row["body"] == "" for row in rows)


def test_ad_publish_stays_paused(client: TestClient, monkeypatch) -> None:
    calls = {"activate": 0}

    class _Ads:
        def create_campaign(self, *, name: str, objective: str, budget) -> AdsCampaignResult:
            _ = (name, objective, budget)
            return AdsCampaignResult(ok=True, provider="stub-ads", is_mock=True, external_id="camp-paused", provider_status="PAUSED")

        def activate_campaign(self, *, external_id: str) -> AdsCampaignResult:
            _ = external_id
            calls["activate"] += 1
            return AdsCampaignResult(ok=True, provider="stub-ads", is_mock=True, external_id="camp-paused", provider_status="ACTIVE")

    monkeypatch.setattr("app.services.content.get_llm_provider", lambda *_args, **_kwargs: _StubLLM(STRUCTURED, is_mock=True))
    monkeypatch.setattr("app.services.content.get_ads_provider", lambda *_args, **_kwargs: _Ads())
    headers = login(client)
    product_id = _ready(client, headers)
    created = client.post("/api/v1/content/generate", headers=headers, json={"product_id": product_id, "ad_channel": "linkedin"})
    draft = next(row for row in created.json()["data"] if row["kind"] == "ad")
    published = client.post(f"/api/v1/content/drafts/{draft['id']}/publish", headers=headers)
    assert published.status_code == 200
    body = published.json()["data"]
    assert body["status"] == "paused"
    assert body["external_id"] == "camp-paused"
    assert calls["activate"] == 0
