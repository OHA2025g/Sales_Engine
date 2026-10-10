import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import Settings, get_settings

LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_VERSION = "202609"
META_GRAPH = "https://graph.facebook.com/v21.0"
_FACEBOOK_ID = re.compile(r"^[0-9]+(?:_[0-9]+)?$")
_FACEBOOK_GUESSED_POST = re.compile(r"^https://(?:www\.)?facebook\.com/\d+/posts/\d+/?$", re.IGNORECASE)
_LINKEDIN_URN = re.compile(r"^urn:li:(?:share|ugcPost|activity):[0-9]+$")
_LINKEDIN_NUMERIC = re.compile(r"^[0-9]+$")
_INSTAGRAM_ID = re.compile(r"^[0-9_]+$")
_INSTAGRAM_CAPTION_LIMIT = 2200
_LOCAL_IMAGE_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def instagram_caption(body: str, link_url: str = "") -> str:
    link = link_url.strip()
    text = body.strip()
    if link and link not in text:
        text = f"{link}\n\n{text}" if text else link
    if len(text) <= _INSTAGRAM_CAPTION_LIMIT:
        return text
    if link and text.startswith(link):
        room = _INSTAGRAM_CAPTION_LIMIT - len(link) - 2
        rest = text[len(link) :].strip()
        if room <= 0:
            return link[:_INSTAGRAM_CAPTION_LIMIT]
        return f"{link}\n\n{rest[:room].rstrip()}"
    return text[:_INSTAGRAM_CAPTION_LIMIT]


def instagram_can_fetch(image_url: str) -> bool:
    parsed = urlsplit(image_url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host in _LOCAL_IMAGE_HOSTS or host.endswith(".local"):
        return False
    return True


@dataclass
class SocialPublishResult:
    ok: bool
    provider: str
    is_mock: bool
    external_id: str = ""
    permalink: str = ""
    reason: str = ""


def _facebook_story_ids(external_id: str) -> tuple[str, str]:
    value = (external_id or "").strip()
    if "_" not in value or not _FACEBOOK_ID.fullmatch(value):
        return "", ""
    page_id, post_id = value.split("_", 1)
    return page_id, post_id


def facebook_permalink_php(external_id: str) -> str:
    page_id, post_id = _facebook_story_ids(external_id)
    if not page_id:
        return ""
    return f"https://www.facebook.com/permalink.php?story_fbid={post_id}&id={page_id}"


def is_usable_facebook_permalink(url: str) -> bool:
    value = (url or "").strip()
    if not value.startswith("https://www.facebook.com/") and not value.startswith("https://facebook.com/"):
        return False
    return _FACEBOOK_GUESSED_POST.fullmatch(value) is None


def public_post_url(channel: str, external_id: str, stored: str = "") -> str:
    kept = (stored or "").strip()
    name = (channel or "").strip().lower()
    if kept.startswith("https://") and (name != "facebook" or is_usable_facebook_permalink(kept)):
        return kept
    value = (external_id or "").strip()
    if not value:
        return ""
    if name == "facebook":
        return facebook_permalink_php(value)
    if name == "linkedin":
        if _LINKEDIN_URN.fullmatch(value):
            return f"https://www.linkedin.com/feed/update/{value}"
        if _LINKEDIN_NUMERIC.fullmatch(value):
            return f"https://www.linkedin.com/feed/update/urn:li:share:{value}"
        return ""
    return ""


def fetch_instagram_permalink(token: str, media_id: str) -> str:
    if not token.strip() or not _INSTAGRAM_ID.fullmatch((media_id or "").strip()):
        return ""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{META_GRAPH}/{media_id.strip()}",
                params={"fields": "permalink", "access_token": token},
            )
        if response.status_code >= 400:
            return ""
        url = str((response.json() or {}).get("permalink") or "").strip()
    except (httpx.HTTPError, ValueError):
        return ""
    if url.startswith("https://www.instagram.com/"):
        return url
    return ""


def fetch_facebook_permalink(token: str, external_id: str) -> str:
    graph_url = ""
    if token.strip() and _FACEBOOK_ID.fullmatch((external_id or "").strip()):
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{META_GRAPH}/{external_id.strip()}",
                    params={"fields": "permalink_url", "access_token": token},
                )
            if response.status_code < 400:
                graph_url = str((response.json() or {}).get("permalink_url") or "").strip()
        except (httpx.HTTPError, ValueError):
            graph_url = ""
    start = facebook_permalink_php(external_id)
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            response = client.get(start or graph_url)
        final = str(response.url)
        if "pfbid" in final or "permalink.php" in final:
            return final
    except (httpx.HTTPError, ValueError):
        pass
    if is_usable_facebook_permalink(graph_url):
        return graph_url
    return start


def resolved_permalink(channel: str, external_id: str, stored: str = "", token: str = "") -> str:
    name = (channel or "").strip().lower()
    if name == "facebook":
        if is_usable_facebook_permalink(stored) and ("pfbid" in stored or "permalink.php" in stored):
            return stored.strip()
        fetched = fetch_facebook_permalink(token, external_id)
        if fetched:
            return fetched
    if name == "instagram":
        built = public_post_url(channel, external_id, stored)
        if built:
            return built
        return fetch_instagram_permalink(token, external_id)
    return public_post_url(channel, external_id, stored)


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
                permalink=public_post_url("linkedin", external_id),
                reason="" if external_id else "LinkedIn returned no post id.",
            )
        except httpx.HTTPError:
            return SocialPublishResult(ok=False, provider="linkedin", is_mock=False, reason="LinkedIn network error.")
        finally:
            if owns:
                client.close()

    def update_commentary(self, *, external_id: str, body: str) -> SocialPublishResult:
        if not external_id.strip():
            return SocialPublishResult(ok=False, provider="linkedin", is_mock=False, reason="This post has no LinkedIn id.")
        owns = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.post(
                f"{LINKEDIN_POSTS_URL}/{quote(external_id.strip(), safe='')}",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Linkedin-Version": LINKEDIN_VERSION,
                    "X-Restli-Protocol-Version": "2.0.0",
                    "X-RestLi-Method": "PARTIAL_UPDATE",
                    "Content-Type": "application/json",
                },
                json={"patch": {"$set": {"commentary": body}}},
            )
            if response.status_code >= 400:
                return SocialPublishResult(
                    ok=False,
                    provider="linkedin",
                    is_mock=False,
                    reason=f"LinkedIn refused the edit ({response.status_code}).",
                )
            return SocialPublishResult(ok=True, provider="linkedin", is_mock=False, external_id=external_id.strip())
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
            return self._publish_instagram(body=body, link_url=link_url, image_url=image_url)
        return self._publish_page(body=body, link_url=link_url)

    def _publish_page(self, *, body: str, link_url: str) -> SocialPublishResult:
        data = {"message": body, "published": "true", "access_token": self._token}
        if link_url.strip():
            data["link"] = link_url.strip()
        return self._post(f"{META_GRAPH}/{self._page_id}/feed", data, provider="facebook")

    def _publish_instagram(self, *, body: str, link_url: str, image_url: str) -> SocialPublishResult:
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
        if not instagram_can_fetch(image_url):
            return SocialPublishResult(
                ok=False,
                provider="instagram",
                is_mock=False,
                reason="Instagram cannot fetch an image hosted on this machine. Paste a public image URL, or publish from a public https address.",
            )
        created = self._post(
            f"{META_GRAPH}/{self._instagram_id}/media",
            {"image_url": image_url.strip(), "caption": instagram_caption(body, link_url), "access_token": self._token},
            provider="instagram",
        )
        if not created.ok:
            return created
        return self._post(
            f"{META_GRAPH}/{self._instagram_id}/media_publish",
            {"creation_id": created.external_id, "access_token": self._token},
            provider="instagram",
        )

    def update_message(self, *, external_id: str, body: str) -> SocialPublishResult:
        if not external_id.strip():
            return SocialPublishResult(ok=False, provider="facebook", is_mock=False, reason="This post has no Facebook id.")
        owns = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.post(
                f"{META_GRAPH}/{external_id.strip()}",
                data={"message": body, "access_token": self._token},
            )
            if response.status_code >= 400:
                return SocialPublishResult(
                    ok=False,
                    provider="facebook",
                    is_mock=False,
                    reason=_meta_refusal("Facebook refused the edit", response),
                )
            return SocialPublishResult(ok=True, provider="facebook", is_mock=False, external_id=external_id.strip())
        except httpx.HTTPError:
            return SocialPublishResult(ok=False, provider="facebook", is_mock=False, reason="Meta network error.")
        finally:
            if owns:
                client.close()

    def _post(self, url: str, data: dict, *, provider: str) -> SocialPublishResult:
        owns = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.post(url, data=data)
            if response.status_code >= 400:
                return SocialPublishResult(ok=False, provider=provider, is_mock=False, reason=_meta_refusal("Meta refused the post", response))
            payload = response.json() if response.content else {}
            external_id = str(payload.get("id") or "")
            permalink = self._permalink(external_id=external_id, provider=provider) if external_id else ""
            return SocialPublishResult(
                ok=bool(external_id),
                provider=provider,
                is_mock=False,
                external_id=external_id,
                permalink=permalink or public_post_url(provider, external_id),
                reason="" if external_id else "Meta returned no post id.",
            )
        except httpx.HTTPError:
            return SocialPublishResult(ok=False, provider=provider, is_mock=False, reason="Meta network error.")
        finally:
            if owns:
                client.close()

    def _permalink(self, *, external_id: str, provider: str) -> str:
        field = "permalink" if provider == "instagram" else "permalink_url"
        getter = getattr(self._client, "get", None)
        owns = False
        client = self._client if getter is not None else None
        if client is None:
            client = httpx.Client(timeout=10.0)
            owns = True
            getter = client.get
        try:
            response = getter(
                f"{META_GRAPH}/{external_id}",
                params={"fields": field, "access_token": self._token},
            )
            if getattr(response, "status_code", 400) >= 400:
                return ""
            payload = response.json() if getattr(response, "content", None) or hasattr(response, "json") else {}
            url = str((payload or {}).get(field) or "").strip()
        except (httpx.HTTPError, ValueError, TypeError):
            return ""
        finally:
            if owns:
                client.close()
        allowed = "https://www.instagram.com/" if provider == "instagram" else "https://www.facebook.com/"
        return url if url.startswith(allowed) else ""


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
