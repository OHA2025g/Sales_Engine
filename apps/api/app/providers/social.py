from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings

LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_VERSION = "202609"
META_GRAPH = "https://graph.facebook.com/v21.0"


@dataclass
class SocialPublishResult:
    ok: bool
    provider: str
    is_mock: bool
    external_id: str = ""
    reason: str = ""


def linkedin_author_urn(organization_id: str) -> str:
    value = organization_id.strip()
    if value.startswith("urn:li:"):
        return value
    return f"urn:li:organization:{value}"


class MockSocialPublisher:
    def __init__(self, channel: str) -> None:
        self._channel = channel

    def publish(self, *, body: str, link_url: str = "", image_url: str = "") -> SocialPublishResult:
        _ = (body, link_url, image_url)
        return SocialPublishResult(
            ok=True,
            provider=f"mock-{self._channel}",
            is_mock=True,
            external_id="",
            reason="Mock post was recorded and was not sent.",
        )


class NotConfiguredSocialPublisher:
    def __init__(self, channel: str, missing: list[str]) -> None:
        self._channel = channel
        self._missing = missing

    def publish(self, *, body: str, link_url: str = "", image_url: str = "") -> SocialPublishResult:
        _ = (body, link_url, image_url)
        needed = ", ".join(self._missing)
        return SocialPublishResult(
            ok=False,
            provider=self._channel,
            is_mock=False,
            reason=f"NOT_CONFIGURED. Set {needed}.",
        )


class LinkedInSocialPublisher:
    def __init__(self, *, token: str, organization_id: str, client: httpx.Client | None = None) -> None:
        self._token = token
        self._author = linkedin_author_urn(organization_id)
        self._client = client

    def publish(self, *, body: str, link_url: str = "", image_url: str = "") -> SocialPublishResult:
        _ = image_url
        payload: dict = {
            "author": self._author,
            "commentary": body,
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if link_url.strip():
            payload["content"] = {"article": {"source": link_url.strip(), "title": body[:200]}}
        owns = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.post(
                LINKEDIN_POSTS_URL,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Linkedin-Version": LINKEDIN_VERSION,
                    "X-Restli-Protocol-Version": "2.0.0",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                return SocialPublishResult(
                    ok=False,
                    provider="linkedin",
                    is_mock=False,
                    reason=f"LinkedIn refused the post ({response.status_code}).",
                )
            external_id = str(response.headers.get("x-restli-id") or "")
            return SocialPublishResult(
                ok=bool(external_id),
                provider="linkedin",
                is_mock=False,
                external_id=external_id,
                reason="" if external_id else "LinkedIn returned no post id.",
            )
        except httpx.HTTPError:
            return SocialPublishResult(ok=False, provider="linkedin", is_mock=False, reason="LinkedIn network error.")
        finally:
            if owns:
                client.close()


class MetaSocialPublisher:
    def __init__(self, *, page_id: str, page_token: str, instagram_id: str = "", client: httpx.Client | None = None) -> None:
        self._page_id = page_id
        self._token = page_token
        self._instagram_id = instagram_id
        self._client = client

    def publish(self, *, body: str, link_url: str = "", image_url: str = "", instagram: bool = False) -> SocialPublishResult:
        if instagram:
            return self._publish_instagram(body=body, image_url=image_url)
        return self._publish_page(body=body, link_url=link_url)

    def _publish_page(self, *, body: str, link_url: str) -> SocialPublishResult:
        data = {"message": body, "access_token": self._token}
        if link_url.strip():
            data["link"] = link_url.strip()
        return self._post(f"{META_GRAPH}/{self._page_id}/feed", data, provider="facebook")

    def _publish_instagram(self, *, body: str, image_url: str) -> SocialPublishResult:
        if not self._instagram_id:
            return SocialPublishResult(
                ok=False,
                provider="instagram",
                is_mock=False,
                reason="NOT_CONFIGURED. Set INSTAGRAM_BUSINESS_ACCOUNT_ID.",
            )
        if not image_url.strip():
            return SocialPublishResult(
                ok=False,
                provider="instagram",
                is_mock=False,
                reason="Instagram posts require a public image URL.",
            )
        created = self._post(
            f"{META_GRAPH}/{self._instagram_id}/media",
            {"image_url": image_url.strip(), "caption": body, "access_token": self._token},
            provider="instagram",
        )
        if not created.ok:
            return created
        return self._post(
            f"{META_GRAPH}/{self._instagram_id}/media_publish",
            {"creation_id": created.external_id, "access_token": self._token},
            provider="instagram",
        )

    def _post(self, url: str, data: dict, *, provider: str) -> SocialPublishResult:
        owns = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.post(url, data=data)
            if response.status_code >= 400:
                return SocialPublishResult(ok=False, provider=provider, is_mock=False, reason=_meta_refusal("Meta refused the post", response))
            payload = response.json() if response.content else {}
            external_id = str(payload.get("id") or "")
            return SocialPublishResult(
                ok=bool(external_id),
                provider=provider,
                is_mock=False,
                external_id=external_id,
                reason="" if external_id else "Meta returned no post id.",
            )
        except httpx.HTTPError:
            return SocialPublishResult(ok=False, provider=provider, is_mock=False, reason="Meta network error.")
        finally:
            if owns:
                client.close()


def posting_gaps(settings: Settings, channel: str) -> list[str]:
    if channel == "linkedin":
        missing: list[str] = []
        if not settings.linkedin_post_access_token:
            missing.append("LINKEDIN_POST_ACCESS_TOKEN")
        if not settings.linkedin_organization_id:
            missing.append("LINKEDIN_ORGANIZATION_ID")
        return missing
    if channel == "facebook":
        missing = []
        if not settings.meta_page_id:
            missing.append("META_PAGE_ID")
        if not settings.meta_page_access_token:
            missing.append("META_PAGE_ACCESS_TOKEN")
        return missing
    if channel == "instagram":
        missing = posting_gaps(settings, "facebook")
        if not settings.instagram_business_account_id:
            missing.append("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        return missing
    if channel == "youtube":
        missing = []
        if not settings.youtube_api_key.strip():
            missing.append("YOUTUBE_API_KEY")
        if not settings.youtube_channel_id.strip():
            missing.append("YOUTUBE_CHANNEL_ID")
        return missing
    if channel == "x":
        missing = []
        if not settings.x_api_key.strip():
            missing.append("X_API_KEY")
        if not settings.x_access_token.strip():
            missing.append("X_ACCESS_TOKEN")
        return missing
    if channel == "whatsapp":
        missing = []
        if not settings.whatsapp_phone_number_id.strip():
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if not settings.whatsapp_access_token.strip():
            missing.append("WHATSAPP_ACCESS_TOKEN")
        return missing
    return ["channel"]


def _meta_refusal(prefix: str, response: httpx.Response) -> str:
    message = ""
    try:
        error = (response.json() or {}).get("error") or {}
        if isinstance(error, dict):
            message = str(error.get("message") or "").replace("\n", " ").strip()
    except ValueError:
        message = ""
    detail = f"{prefix} ({response.status_code})."
    return f"{detail} {message[:180]}".strip()


def reaches_provider(mode: str) -> bool:
    return (mode or "").strip().lower() == "live"


def get_social_publisher(channel: str):
    settings = get_settings()
    normalized = channel.strip().lower()
    if normalized == "linkedin":
        mode = (settings.linkedin_posting_mode or "mock").strip().lower()
        if mode == "live":
            missing = posting_gaps(settings, "linkedin")
            if missing:
                return NotConfiguredSocialPublisher("linkedin", missing)
            return LinkedInSocialPublisher(
                token=settings.linkedin_post_access_token,
                organization_id=settings.linkedin_organization_id,
            )
        return MockSocialPublisher("linkedin")
    if normalized in {"facebook", "instagram"}:
        mode = (settings.meta_posting_mode or "mock").strip().lower()
        if reaches_provider(mode):
            missing = posting_gaps(settings, normalized)
            if missing:
                return NotConfiguredSocialPublisher(normalized, missing)
            return MetaSocialPublisher(
                page_id=settings.meta_page_id,
                page_token=settings.meta_page_access_token,
                instagram_id=settings.instagram_business_account_id,
            )
        return MockSocialPublisher(normalized)
    return NotConfiguredSocialPublisher(normalized or "social", ["channel"])
