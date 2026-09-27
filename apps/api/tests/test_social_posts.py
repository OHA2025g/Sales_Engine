from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.providers.social import LinkedInSocialPublisher
from tests.conftest import login


def test_mock_linkedin_post_is_not_sent(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("LINKEDIN_POSTING_MODE", "mock")
    get_settings.cache_clear()
    headers = login(client)
    try:
        created = client.post(
            "/api/v1/social/posts",
            headers=headers,
            json={"channel": "linkedin", "body": "Hello from the demo."},
        )
        assert created.status_code == 200
        row = created.json()["data"]
        assert row["is_mock"] is True
        assert row["status"] == "mock"
        assert row["provider"] == "mock-linkedin"
        assert row["external_id"] == ""
        listed = client.get("/api/v1/social/posts", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == row["id"] for item in listed.json()["data"])
    finally:
        monkeypatch.delenv("LINKEDIN_POSTING_MODE", raising=False)
        get_settings.cache_clear()


def test_live_linkedin_without_token_is_not_a_silent_post(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("LINKEDIN_POSTING_MODE", "live")
    monkeypatch.setenv("LINKEDIN_POST_ACCESS_TOKEN", "")
    monkeypatch.setenv("LINKEDIN_ORGANIZATION_ID", "")
    get_settings.cache_clear()
    headers = login(client)
    try:
        created = client.post(
            "/api/v1/social/posts",
            headers=headers,
            json={"channel": "linkedin", "body": "This must not publish."},
        )
        assert created.status_code == 200
        row = created.json()["data"]
        assert row["is_mock"] is False
        assert row["status"] == "failed"
        assert "NOT_CONFIGURED" in row["error"]
        assert "LINKEDIN_POST_ACCESS_TOKEN" in row["error"]
    finally:
        monkeypatch.delenv("LINKEDIN_POSTING_MODE", raising=False)
        monkeypatch.delenv("LINKEDIN_POST_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("LINKEDIN_ORGANIZATION_ID", raising=False)
        get_settings.cache_clear()


def test_linkedin_publisher_posts_organization_feed(monkeypatch) -> None:
    monkeypatch.setenv("LINKEDIN_ORGANIZATION_ID", "143930363")
    get_settings.cache_clear()

    class _Response:
        status_code = 201
        headers = {"x-restli-id": "urn:li:share:1"}
        content = b""

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
        result = LinkedInSocialPublisher(token="test-token", organization_id="143930363", client=client).publish(body="Ship the note.")  # type: ignore[arg-type]
        assert client.url == "https://api.linkedin.com/rest/posts"
        assert client.body is not None
        assert client.body["author"] == "urn:li:organization:143930363"
        assert client.body["commentary"] == "Ship the note."
        assert result.ok is True
        assert result.is_mock is False
        assert result.external_id == "urn:li:share:1"
    finally:
        monkeypatch.delenv("LINKEDIN_ORGANIZATION_ID", raising=False)
        get_settings.cache_clear()
