from app.core.config import get_settings
from app.providers.channel_search import (
    ApifyChannelSearch,
    ChannelHit,
    ChannelOutcome,
    ChannelSearchOutcome,
    GeminiChannelSearch,
    GoogleCseChannelSearch,
    grounding_hits,
    is_channel_post,
    parse_apify_items,
)
from tests.conftest import login


class _Response:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_social_post_urls_are_kept_and_profiles_are_not() -> None:
    assert is_channel_post("facebook", "https://www.facebook.com/acme/posts/1") is True
    assert is_channel_post("facebook", "https://www.facebook.com/login") is False
    assert is_channel_post("instagram", "https://www.instagram.com/p/ABC123/") is True
    assert is_channel_post("instagram", "https://www.instagram.com/acme/") is False
    assert is_channel_post("linkedin", "https://www.linkedin.com/posts/activity-1") is True
    assert is_channel_post("linkedin", "https://www.linkedin.com/in/someone") is False
    assert is_channel_post("google", "https://example.com/article") is True


def test_gemini_ignores_model_text_without_sources() -> None:
    payload = {
        "candidates": [
            {
                "content": {"parts": [{"text": "1. Invented post https://www.facebook.com/acme/posts/9"}]},
                "groundingMetadata": {"groundingChunks": []},
            }
        ]
    }
    assert grounding_hits(payload, "facebook") == []


def test_gemini_keeps_only_grounded_sources() -> None:
    payload = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Invented https://www.instagram.com/p/FAKE/"}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": "https://www.instagram.com/p/REAL1/", "title": "Real reel"}},
                        {"web": {"uri": "https://www.instagram.com/acme/", "title": "Profile"}},
                    ]
                },
            }
        ]
    }
    hits = grounding_hits(payload, "instagram")
    assert [hit.url for hit in hits] == ["https://www.instagram.com/p/REAL1/"]
    assert hits[0].rank == 1


def test_apify_groups_results_by_channel_and_keeps_google_rank() -> None:
    items = [
        {
            "searchQuery": {"term": "warehouse robots"},
            "organicResults": [
                {"title": "Web", "url": "https://example.com/robots", "description": "A", "position": 1},
            ],
        },
        {
            "searchQuery": {"term": "warehouse robots site:facebook.com"},
            "organicResults": [
                {"title": "Login", "url": "https://www.facebook.com/login", "description": "no", "position": 1},
                {"title": "Fb post", "url": "https://www.facebook.com/acme/posts/2", "description": "hi", "position": 2},
            ],
        },
        {
            "searchQuery": {"term": "warehouse robots site:instagram.com"},
            "organicResults": [
                {"title": "Ig", "url": "https://www.instagram.com/reel/ABC/", "description": "clip", "position": 4},
            ],
        },
        {
            "searchQuery": {"term": "warehouse robots site:linkedin.com/posts"},
            "organicResults": [
                {"title": "Person", "url": "https://www.linkedin.com/in/someone", "description": "no", "position": 1},
                {"title": "Li", "url": "https://www.linkedin.com/posts/activity-9", "description": "note", "position": 3},
            ],
        },
    ]
    grouped = parse_apify_items(items)
    assert grouped["google"][0].rank == 1
    assert grouped["facebook"][0].rank == 2
    assert grouped["facebook"][0].title == "Fb post"
    assert grouped["instagram"][0].rank == 4
    assert grouped["linkedin"][0].rank == 3
    assert len(grouped["linkedin"]) == 1


def test_google_cse_ranks_each_channel() -> None:

    class _Client:
        def get(self, url: str, params: dict | None = None):
            _ = url
            query = (params or {}).get("q", "")
            if "site:facebook.com" in query:
                return _Response(
                    {
                        "items": [
                            {"title": "Other", "link": "https://example.com/x", "snippet": "no"},
                            {"title": "Fb", "link": "https://www.facebook.com/acme/posts/1", "snippet": "warehouse robots"},
                        ]
                    }
                )
            if "site:instagram.com" in query:
                return _Response({"items": [{"title": "Profile", "link": "https://www.instagram.com/acme/", "snippet": "no"}]})
            if "site:linkedin.com" in query:
                return _Response(
                    {"items": [{"title": "Li", "link": "https://www.linkedin.com/posts/activity-1", "snippet": "warehouse robots"}]}
                )
            return _Response(
                {"items": [{"title": f"Result {index}", "link": f"https://example.com/{index}", "snippet": "warehouse robots"} for index in range(1, 11)]}
            )

    outcome = GoogleCseChannelSearch("test-key", "test-cx", client=_Client()).search("warehouse robots")
    by_name = {channel.channel: channel for channel in outcome.channels}
    assert [hit.rank for hit in by_name["google"].hits] == list(range(1, 11))
    assert by_name["facebook"].hits[0].rank == 2
    assert by_name["instagram"].hits == []
    assert by_name["instagram"].mode == "live"
    assert by_name["linkedin"].hits[0].url.endswith("/posts/activity-1")
    assert outcome.provider == "google_cse"


def test_google_cse_hides_the_key_when_search_is_refused() -> None:
    class _Client:
        def get(self, url: str, params: dict | None = None):
            _ = (url, params)
            return _Response({"error": {"message": "bad key test-key"}}, status_code=403)

    outcome = GoogleCseChannelSearch("test-key", "test-cx", client=_Client()).search("warehouse robots")
    assert outcome.channels[0].mode == "failed"
    assert "test-key" not in outcome.channels[0].reason
    assert "[redacted]" in outcome.channels[0].reason


def test_apify_search_reads_ranked_dataset_items() -> None:
    class _Client:
        def post(self, url: str, headers: dict | None = None, json: dict | None = None, params: dict | None = None):
            _ = (url, headers, params)
            assert "site:instagram.com" in (json or {})["queries"]
            return _Response({"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "data-1"}})

        def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            _ = (headers, params)
            assert url.endswith("/datasets/data-1/items")
            return _Response(
                [
                    {
                        "searchQuery": {"term": "warehouse robots"},
                        "organicResults": [{"title": "Web", "url": "https://example.com/a", "description": "warehouse robots", "position": 1}],
                    }
                ]
            )

    outcome = ApifyChannelSearch("token", "apify/google-search-scraper", client=_Client()).search("warehouse robots")
    assert outcome.provider == "apify"
    assert outcome.channels[0].hits[0].title == "Web"
    assert outcome.channels[0].mode == "live"


def test_unrelated_facebook_posts_are_removed() -> None:
    class _Client:
        def post(self, url: str, headers: dict | None = None, json: dict | None = None, params: dict | None = None):
            _ = (url, headers, json, params)
            return _Response({"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "data-1"}})

        def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            _ = (url, headers, params)
            return _Response(
                [
                    {
                        "searchQuery": {"term": "pgdm marketing course site:facebook.com"},
                        "organicResults": [
                            {
                                "title": "Bishop's Salon & Day Spa",
                                "url": "https://www.facebook.com/bishopsalon/posts/1",
                                "description": "We offer color services and blowouts.",
                                "position": 2,
                            },
                            {
                                "title": "PGDM Marketing Program",
                                "url": "https://www.facebook.com/college/posts/2",
                                "description": "A two-year PGDM marketing course.",
                                "position": 5,
                            },
                        ],
                    }
                ]
            )

    outcome = ApifyChannelSearch("token", "apify/google-search-scraper", client=_Client()).search("pgdm marketing course")
    by_name = {channel.channel: channel for channel in outcome.channels}
    assert [hit.title for hit in by_name["facebook"].hits] == ["PGDM Marketing Program"]
    assert by_name["facebook"].hits[0].rank == 5
    assert by_name["google"].hits == []
    assert by_name["google"].reason == "No public posts matched this keyword."


def test_unconfigured_search_invents_nothing(client, monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_SEARCH_PROVIDER", "auto")
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "")
    monkeypatch.setenv("GOOGLE_CSE_CX", "")
    monkeypatch.setenv("APIFY_API_TOKEN", "")
    monkeypatch.setenv("APIFY_TOKEN", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    headers = login(client)
    try:
        created = client.post("/api/v1/channel-search", headers=headers, json={"query": "warehouse robots"})
        assert created.status_code == 200
        body = created.json()["data"]
        assert body["provider"] == "not_configured"
        assert body["status"] == "not_configured"
        assert all(channel["hits"] == [] for channel in body["channels"])
        assert [channel["channel"] for channel in body["channels"]] == ["google", "facebook", "instagram", "linkedin"]
        listed = client.get("/api/v1/channel-search", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == body["id"] for item in listed.json()["data"])
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_search_stores_provider_hits_without_calling_a_network(client, monkeypatch) -> None:
    class _Provider:
        def search(self, query: str) -> ChannelSearchOutcome:
            assert query == "warehouse robots"
            return ChannelSearchOutcome(
                provider="google_cse",
                channels=[
                    ChannelOutcome("google", "live", "google_cse", "", [ChannelHit(1, "Ranked warehouse robots", "https://example.com/a", "snip")]),
                    ChannelOutcome("facebook", "live", "google_cse", "No public posts were returned for this keyword.", []),
                    ChannelOutcome("instagram", "failed", "google_cse", "Google search could not be reached.", []),
                    ChannelOutcome("linkedin", "live", "google_cse", "", [ChannelHit(3, "Post", "https://www.linkedin.com/posts/1", "warehouse robots")]),
                ],
            )

    monkeypatch.setattr("app.services.channel_search.get_channel_search_provider", lambda: _Provider())
    headers = login(client)
    created = client.post("/api/v1/channel-search", headers=headers, json={"query": "  warehouse   robots  "})
    assert created.status_code == 200
    body = created.json()["data"]
    assert body["status"] == "partial"
    assert body["query"] == "warehouse robots"
    google = body["channels"][0]
    linkedin = body["channels"][3]
    assert google["hits"][0]["rank"] == 1
    assert linkedin["hits"][0]["rank"] == 3
    denied = client.post("/api/v1/channel-search", json={"query": "warehouse robots"})
    assert denied.status_code == 401


def test_short_query_is_rejected(client) -> None:
    headers = login(client)
    rejected = client.post("/api/v1/channel-search", headers=headers, json={"query": "a"})
    assert rejected.status_code == 422


def test_gemini_provider_does_not_store_ungrounded_text() -> None:
    class _Client:
        def post(self, url: str, headers: dict | None = None, json: dict | None = None):
            _ = (url, headers)
            assert json is not None
            assert json["tools"] == [{"google_search": {}}]
            return _Response(
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Top post https://example.com/invented"}]},
                            "groundingMetadata": {
                                "groundingChunks": [{"web": {"uri": "https://example.com/real", "title": "Warehouse robots"}}]
                            },
                        }
                    ]
                }
            )

    outcome = GeminiChannelSearch("key", "gemini-test", client=_Client()).search("warehouse robots")
    assert [hit.url for hit in outcome.channels[0].hits] == ["https://example.com/real"]
    assert all("invented" not in hit.url for channel in outcome.channels for hit in channel.hits)
