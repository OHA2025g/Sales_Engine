import json

import httpx
from fastapi.testclient import TestClient

from app.ai.providers import CompletionResult
from app.providers.lead_discovery import (
    ApifyLeadDiscoveryProvider,
    DiscoveredLead,
    DiscoveryQuery,
    DiscoveryResult,
    MockLeadDiscoveryProvider,
    map_dataset_items,
)
from app.services.discovery import clean_domain, infer_company_domain
from app.services.discovery_query import build_discovery_query
from tests.conftest import login


class FixtureDiscovery:
    def __init__(self, email: str = "priya.nair@fixture.example", first: str = "Priya", last: str = "Nair") -> None:
        self.email = email
        self.first = first
        self.last = last

    def health(self) -> dict:
        return {"provider": "fixture", "is_mock": True, "connected": False, "reason": "test fixture"}

    def discover(self, query) -> DiscoveryResult:
        _ = query
        slug = (self.last or "priya").lower().replace(" ", "-")
        person = DiscoveredLead(
            self.first,
            self.last,
            self.email,
            "CIO",
            "Fixture Bank",
            f"https://linkedin.com/in/{slug}",
        )
        return DiscoveryResult(
            candidates=[person, person],
            provider="fixture",
            is_mock=True,
            connected=False,
            reason="test fixture",
        )


def test_map_dataset_never_invents_missing_names() -> None:
    rows = map_dataset_items(
        [
            {"firstName": "Ada", "lastName": "Khan", "email": "ada@example.com", "title": "CTO", "companyName": "Harbor"},
            {"email": "nobody@example.com"},
        ]
    )
    assert len(rows) == 1
    assert rows[0].first_name == "Ada"
    assert rows[0].company_name == "Harbor"


def test_discover_persists_and_dedupes(client: TestClient, monkeypatch) -> None:
    fixture = FixtureDiscovery(email="priya.dedupe@fixture.example", first="Priya", last="Dedupe")
    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: fixture)
    headers = login(client)
    first = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert first.status_code == 200, first.text
    body = first.json()["data"]
    assert body["created"] == 1
    assert body["skipped"].get("duplicate_email") == 1
    second = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert second.status_code == 200
    assert second.json()["data"]["created"] == 0
    assert second.json()["data"]["skipped"].get("duplicate_email") == 2
    leads = client.get("/api/v1/leads", headers=headers, params={"q": "Dedupe"}).json()["data"]
    assert any(row["source"] == "ai_discovery" and row["email"] == fixture.email for row in leads)
    assert all(not row["consent_email"] for row in leads if row["email"] == fixture.email)


def test_discover_skips_opt_out(client: TestClient, monkeypatch) -> None:
    headers = login(client)
    opted = client.post(
        "/api/v1/contacts",
        headers=headers,
        json={"first_name": "No", "last_name": "Hunt", "email": "no.hunt@fixture.example", "opt_out": True},
    )
    assert opted.status_code == 200

    class OptOutFixture(FixtureDiscovery):
        def discover(self, query) -> DiscoveryResult:
            _ = query
            return DiscoveryResult(
                candidates=[
                    DiscoveredLead("No", "Hunt", "no.hunt@fixture.example", "CISO", "Blocked Co", ""),
                ],
                provider="fixture",
                is_mock=True,
                connected=False,
                reason="test",
            )

    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: OptOutFixture())
    run = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert run.status_code == 200
    assert run.json()["data"]["created"] == 0
    assert run.json()["data"]["skipped"].get("opt_out") == 1


def test_human_add_and_discovery_source_guard(client: TestClient) -> None:
    headers = login(client)
    human = client.post(
        "/api/v1/leads",
        headers=headers,
        json={"first_name": "Offline", "last_name": "Find", "email": "offline.find@example.com", "company_name": "Paper Co"},
    )
    assert human.status_code == 200
    assert human.json()["data"]["source"] == "human"
    refused = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "first_name": "Fake",
            "last_name": "Discover",
            "email": "fake.discover@example.com",
            "source": "ai_discovery",
        },
    )
    assert refused.status_code == 422


def test_import_sets_source_import(client: TestClient) -> None:
    headers = login(client)
    commit = client.post(
        "/api/v1/imports/commit",
        headers=headers,
        json={"entity": "leads", "rows": [{"first_name": "Csv", "last_name": "Row", "email": "csv.row@example.com"}]},
    )
    assert commit.status_code == 200
    leads = client.get("/api/v1/leads", headers=headers, params={"q": "Csv"}).json()["data"]
    assert any(row["source"] == "import" for row in leads)


def test_discovery_is_tenant_scoped(client: TestClient, monkeypatch) -> None:
    fixture = FixtureDiscovery(email="priya.scope@fixture.example", first="Priya", last="Scope")
    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: fixture)
    agrayian = login(client, "admin@agrayian.demo")
    northline = login(client, "admin@northline.demo")
    created = client.post("/api/v1/discovery/run", headers=agrayian, json={})
    assert created.status_code == 200
    lead_id = created.json()["data"]["lead_ids"][0]
    leaked = client.get(f"/api/v1/leads/{lead_id}", headers=northline)
    assert leaked.status_code == 404
    other = client.get("/api/v1/leads", headers=northline, params={"q": "Scope"}).json()["data"]
    assert all(row["email"] != fixture.email for row in other)


def test_map_dataset_skips_malformed_and_keeps_provider_ref() -> None:
    rows = map_dataset_items(
        [
            "not-a-dict",
            {"firstName": "Only"},
            {
                "firstName": "Sam",
                "lastName": "Rao",
                "profileUrl": "https://linkedin.com/in/sam-rao",
                "id": "urn:li:person:1",
                "companyName": "Harbor",
            },
        ]
    )
    assert len(rows) == 1
    assert rows[0].provider_ref == "urn:li:person:1"
    assert rows[0].linkedin_url.endswith("sam-rao")


def test_map_harvest_search_actor_fields() -> None:
    rows = map_dataset_items(
        [
            {
                "firstName": "Asha",
                "lastName": "Mehta",
                "headline": "Technology leader",
                "linkedinUrl": "https://www.linkedin.com/in/asha",
                "currentPosition": [
                    {"companyName": "Harbor", "position": "Chief Information Officer"},
                ],
                "companyWebsites": [{"domain": "harbor.example", "url": "https://www.harbor.example"}],
                "emails": [{"email": "asha@harbor.example", "deliverable": True}],
            }
        ]
    )
    assert rows[0].title == "Chief Information Officer"
    assert rows[0].company_name == "Harbor"
    assert rows[0].company_website == "https://www.harbor.example"
    assert rows[0].email == "asha@harbor.example"
    assert rows[0].linkedin_url.endswith("/asha")


def test_map_dataset_keeps_company_website() -> None:
    rows = map_dataset_items(
        [
            {
                "firstName": "Asha",
                "lastName": "Mehta",
                "companyName": "Harbor",
                "companyWebsite": "https://www.harbor.example/about",
            }
        ]
    )
    assert rows[0].company_website == "https://www.harbor.example/about"
    assert clean_domain(rows[0].company_website) == "harbor.example"


def test_llm_fills_domain_when_scrape_has_no_website(monkeypatch) -> None:
    class _Llm:
        def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
            _ = (prompt, system, model, reasoning)
            return CompletionResult(
                text="harbor.example",
                provider="gemini",
                model="gemini-2.5-flash",
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
                is_mock=False,
                estimated_cost=0.0,
            )

    monkeypatch.setattr("app.services.discovery.get_llm_provider", lambda *args, **kwargs: _Llm())
    domain = infer_company_domain(DiscoveredLead("Asha", "Mehta", "", "CIO", "Harbor Payments", "https://linkedin.com/in/asha"))
    assert domain == "harbor.example"
    assert infer_company_domain(DiscoveredLead("Asha", "Mehta", "", "CIO", "Harbor", "", company_website="https://www.harbor.example")) == "harbor.example"
    assert clean_domain("gmail.com") == ""


def test_query_builder_uses_icp_filters() -> None:
    class FakeICP:
        industries = "technology,unknown-vertical"
        geographies = "india"
        min_employees = 200
        max_employees = 500
        description = "AI buyers"
        personas = "CIO"
        seniorities = "cxo,made-up"
        job_functions = "information technology"
        target_companies = "https://linkedin.com/company/harbor"
        keywords = "revenue OS"

    query = build_discovery_query(FakeICP(), max_items=8)
    assert "CIO" in query.job_titles
    assert "Chief Information Officer" in query.job_titles
    assert "information technology" not in query.job_titles
    assert "13" in query.function_ids
    assert "India" in query.location_names
    assert "310" in query.seniority_ids
    assert "made-up" not in query.seniority_ids
    assert "4" in query.industry_ids
    assert "E" in query.company_headcount
    assert "D" in query.company_headcount
    assert "revenue OS" in query.search_query
    assert "unknown-vertical" in query.search_query
    assert query.actor_search_query == ""


def test_search_actor_requests_email_mode() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runs"):
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "ds-1"}})
        return httpx.Response(
            200,
            json=[{"firstName": "Asha", "lastName": "Mehta", "email": {"email": "asha@harbor.example"}, "linkedinUrl": "https://linkedin.com/in/asha"}],
        )

    provider = ApifyLeadDiscoveryProvider(
        token="token",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=10,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.discover(DiscoveryQuery(search_query="CIO"))
    body = json.loads(str(seen["body"]))
    assert body["profileScraperMode"] == "Full + email search"
    assert body["maxItems"] == 10
    assert body["searchQuery"] == "CIO"
    assert result.candidates[0].email == "asha@harbor.example"


def test_search_actor_omits_keyword_query_when_titles_exist() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runs"):
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "ds-1"}})
        return httpx.Response(200, json=[])

    provider = ApifyLeadDiscoveryProvider(
        token="token",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=10,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.discover(
        DiscoveryQuery(
            search_query="AI transformation",
            keywords="AI transformation",
            job_titles=("CIO", "Chief Information Officer"),
            location_names=("India", "United Arab Emirates"),
            function_ids=("13",),
        )
    )
    body = json.loads(str(seen["body"]))
    assert "searchQuery" not in body
    assert body["currentJobTitles"] == ["CIO", "Chief Information Officer"]
    assert body["locations"] == ["India", "United Arab Emirates"]
    assert body["functionIds"] == ["13"]
    assert result.reason
    assert result.candidates == []


def test_harvest_batch_never_exceeds_30() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runs"):
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "ds-1"}})
        return httpx.Response(200, json=[])

    provider = ApifyLeadDiscoveryProvider(
        token="token",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.discover(DiscoveryQuery(search_query="CIO", max_items=100))
    body = json.loads(str(seen["body"]))
    assert body["maxItems"] == 30


def test_empty_apify_dataset_invents_nobody() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runs"):
            return httpx.Response(200, json={"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "ds-1"}})
        return httpx.Response(200, json=[])

    provider = ApifyLeadDiscoveryProvider(
        token="token",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=10,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.discover(DiscoveryQuery(search_query="CIO", industries="bfsi", geographies="india"))
    assert result.candidates == []
    assert result.provider == "apify"
    assert result.is_mock is False


def test_apify_rate_limit_and_auth_and_timeout() -> None:
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate"})

    limited_provider = ApifyLeadDiscoveryProvider(
        token="token",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=5,
        client=httpx.Client(transport=httpx.MockTransport(limited)),
    )
    limited_result = limited_provider.discover(DiscoveryQuery(search_query="CIO"))
    assert limited_result.candidates == []
    assert limited_result.failure_class == "RATE_LIMIT"

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "auth"})

    auth_provider = ApifyLeadDiscoveryProvider(
        token="bad",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=5,
        client=httpx.Client(transport=httpx.MockTransport(unauthorized)),
    )
    auth_result = auth_provider.discover(DiscoveryQuery(search_query="CIO"))
    assert auth_result.failure_class == "AUTHENTICATION"

    class TimeoutClient(httpx.Client):
        def post(self, *args, **kwargs):
            raise httpx.TimeoutException("slow")

    timeout_provider = ApifyLeadDiscoveryProvider(
        token="token",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=5,
        client=TimeoutClient(),
    )
    timeout_result = timeout_provider.discover(DiscoveryQuery(search_query="CIO"))
    assert timeout_result.candidates == []
    assert timeout_result.failure_class == "TRANSIENT"


def test_harvest_free_limit_is_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runs"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "run-limit",
                        "status": "SUCCEEDED",
                        "defaultDatasetId": "ds-empty",
                        "statusMessage": "free user run limit reached",
                    }
                },
            )
        return httpx.Response(200, json=[])

    provider = ApifyLeadDiscoveryProvider(
        token="token",
        actor_id="harvestapi/linkedin-profile-search",
        max_items=10,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.discover(DiscoveryQuery(search_query="CIO"))
    assert result.candidates == []
    assert result.failure_class == "RATE_LIMIT"
    assert result.connected is False
    assert "Upgrade the Apify account" in result.reason


def test_valid_search_results_persist_provenance(client: TestClient, monkeypatch) -> None:
    class SearchFixture:
        def health(self) -> dict:
            return {"provider": "apify", "is_mock": False, "connected": True, "reason": "stub"}

        def discover(self, query) -> DiscoveryResult:
            _ = query
            return DiscoveryResult(
                candidates=[
                    DiscoveredLead(
                        "Asha",
                        "Mehta",
                        "asha.mehta@harbor.example",
                        "CIO",
                        "Harbor",
                        "https://linkedin.com/in/asha-mehta",
                        provider_ref="person-asha",
                        confidence=70,
                        source_url="https://linkedin.com/in/asha-mehta",
                    )
                ],
                provider="apify",
                is_mock=False,
                connected=True,
            )

    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: SearchFixture())
    headers = login(client)
    run = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert run.status_code == 200, run.text
    lead_id = run.json()["data"]["lead_ids"][0]
    lead = client.get(f"/api/v1/leads/{lead_id}", headers=headers).json()["data"]
    assert lead["linkedin_url"].endswith("asha-mehta")
    assert lead["provider_ref"] == "person-asha"
    assert lead["discovery_provider"] == "apify"
    assert lead["consent_email"] is False


def test_linkedin_url_dedupe(client: TestClient, monkeypatch) -> None:
    class UrlFixture:
        def health(self) -> dict:
            return {"provider": "fixture", "is_mock": True, "connected": False, "reason": "test"}

        def discover(self, query) -> DiscoveryResult:
            _ = query
            return DiscoveryResult(
                candidates=[
                    DiscoveredLead("One", "Url", "", "CIO", "Harbor", "https://linkedin.com/in/same-url"),
                    DiscoveredLead("Two", "Url", "", "CTO", "Harbor", "https://linkedin.com/in/same-url"),
                ],
                provider="fixture",
                is_mock=True,
                connected=False,
            )

    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: UrlFixture())
    headers = login(client)
    run = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert run.json()["data"]["created"] == 1
    assert run.json()["data"]["skipped"].get("duplicate_linkedin") == 1


def test_open_circuit_returns_last_vendor_error(client: TestClient, monkeypatch) -> None:
    class ShouldNotRun:
        def health(self) -> dict:
            return {"provider": "apify", "is_mock": False, "connected": True, "reason": ""}

        def discover(self, query) -> DiscoveryResult:
            raise AssertionError("vendor should not run while the circuit is open")

    class FakeHealth:
        last_error_summary = "HarvestAPI blocked this Apify free-plan run."

    monkeypatch.setattr("app.services.discovery.get_lead_discovery_provider", lambda *args, **kwargs: ShouldNotRun())
    monkeypatch.setattr("app.services.discovery.is_circuit_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.services.discovery.get_health_state", lambda *args, **kwargs: FakeHealth())
    headers = login(client)
    run = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert run.status_code == 200
    body = run.json()["data"]
    assert body["created"] == 0
    assert "HarvestAPI" in body["reason"]


def test_mock_discovery_without_people(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.discovery.get_lead_discovery_provider",
        lambda *args, **kwargs: MockLeadDiscoveryProvider(),
    )
    monkeypatch.setattr(
        "app.services.discovery.get_lead_discovery_provider",
        lambda *args, **kwargs: MockLeadDiscoveryProvider(),
    )
    headers = login(client)
    health = client.get("/api/v1/discovery/health", headers=headers)
    assert health.status_code == 200
    run = client.post("/api/v1/discovery/run", headers=headers, json={})
    assert run.status_code == 200
    body = run.json()["data"]
    assert body["created"] == 0
    assert body["is_mock"] is True
