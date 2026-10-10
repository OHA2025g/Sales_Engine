"""Public post search for Google, Facebook, Instagram, and LinkedIn.

Rank is the Google result position for the keyword. Facebook, Instagram, and
LinkedIn keep only public post URLs on that network. A missing provider returns
no hits and does not invent posts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

CHANNELS = ("google", "facebook", "instagram", "linkedin")
RESULT_LIMIT = 10
NO_MATCH_REASON = "No public posts matched this keyword."
_STOPWORDS = {
    "a",
    "an",
    "and",
    "or",
    "the",
    "for",
    "of",
    "to",
    "in",
    "on",
    "with",
    "by",
    "from",
    "at",
    "is",
    "it",
    "this",
    "that",
    "your",
    "our",
    "how",
    "what",
    "why",
    "when",
    "where",
    "who",
    "be",
    "as",
    "are",
    "was",
    "into",
    "about",
}
CSE_URL = "https://www.googleapis.com/customsearch/v1"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROUNDING_HOSTS = {"vertexaisearch.cloud.google.com", "www.google.com", "google.com"}

CHANNEL_SITE = {
    "google": "",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "linkedin": "linkedin.com/posts",
}

POST_MARKERS = {
    "instagram": ("/p/", "/reel/", "/reels/", "/tv/"),
    "linkedin": ("/posts", "/feed/update", "/pulse/"),
}
FACEBOOK_SKIPPED_PREFIXES = ("/login", "/sharer", "/policies", "/privacy", "/help", "/settings", "/recover", "/dialog")

NOT_CONFIGURED_DETAIL = (
    "Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX for ranked Google results. "
    "APIFY_API_TOKEN or GEMINI_API_KEY with a Gemini model can be used instead. "
    "No posts are invented."
)


@dataclass
class ChannelHit:
    rank: int
    title: str
    url: str
    snippet: str


@dataclass
class ChannelOutcome:
    channel: str
    mode: str
    provider: str
    reason: str
    hits: list[ChannelHit] = field(default_factory=list)


@dataclass
class ChannelSearchOutcome:
    provider: str
    channels: list[ChannelOutcome]


def public_http_url(value: str) -> str:
    cleaned = value.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return cleaned[:1000]


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_matches(url: str, host: str) -> bool:
    name = hostname(url)
    expected = host.lower()
    return name == expected or name.endswith(f".{expected}")


def is_channel_post(channel: str, url: str) -> bool:
    if channel == "google":
        return True
    if channel == "facebook":
        return _facebook_result(url)
    host = {"instagram": "instagram.com", "linkedin": "linkedin.com"}.get(channel, "")
    if not host or not host_matches(url, host):
        return False
    path = (urlparse(url).path or "").lower()
    query = (urlparse(url).query or "").lower()
    return any(marker in path or marker in query for marker in POST_MARKERS.get(channel, ()))


def _facebook_result(url: str) -> bool:
    if not host_matches(url, "facebook.com"):
        return False
    path = (urlparse(url).path or "").lower()
    if path in {"", "/"}:
        return False
    return not any(path.startswith(prefix) for prefix in FACEBOOK_SKIPPED_PREFIXES)


def clean_title(value: str) -> str:
    return " ".join(value.split())[:300]


def _redact(text: str, *secrets: str) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return " ".join(cleaned.split())[:400]


def _rank(value: Any, fallback: int) -> int:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return fallback
    return rank if rank > 0 else fallback


def hits_from_items(channel: str, items: list[Any]) -> list[ChannelHit]:
    hits: list[ChannelHit] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        url = public_http_url(str(item.get("link") or item.get("url") or ""))
        title = clean_title(str(item.get("title") or ""))
        if not url or not title or not is_channel_post(channel, url):
            continue
        snippet = " ".join(str(item.get("snippet") or item.get("description") or "").split())[:500]
        hits.append(ChannelHit(rank=_rank(item.get("position") or item.get("rank"), index), title=title, url=url, snippet=snippet))
    return _trim(hits)


def _trim(hits: list[ChannelHit]) -> list[ChannelHit]:
    seen: set[str] = set()
    kept: list[ChannelHit] = []
    for hit in sorted(hits, key=lambda item: item.rank):
        if hit.url in seen:
            continue
        seen.add(hit.url)
        kept.append(hit)
        if len(kept) == RESULT_LIMIT:
            break
    return kept


def query_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 2 or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def relevant_hits(query: str, hits: list[ChannelHit]) -> list[ChannelHit]:
    tokens = query_tokens(query)
    if not tokens:
        return hits
    needed = 1 if len(tokens) == 1 else 2
    kept: list[ChannelHit] = []
    for hit in hits:
        text = f"{hit.title} {hit.snippet}".lower()
        found = sum(1 for token in tokens if re.search(rf"\b{re.escape(token)}\b", text))
        if found >= needed:
            kept.append(hit)
    return kept


def channel_query(channel: str, query: str) -> str:
    site = CHANNEL_SITE[channel]
    if not site:
        return query
    return f"{query} site:{site}"


def channel_from_term(term: str) -> str | None:
    lowered = term.lower()
    if "site:facebook.com" in lowered:
        return "facebook"
    if "site:instagram.com" in lowered:
        return "instagram"
    if "site:linkedin.com" in lowered:
        return "linkedin"
    if term.strip():
        return "google"
    return None


def search_queries(query: str) -> str:
    return "\n".join(channel_query(channel, query) for channel in CHANNELS)


def parse_apify_items(items: list[Any]) -> dict[str, list[ChannelHit]]:
    grouped: dict[str, list[ChannelHit]] = {channel: [] for channel in CHANNELS}
    for item in items:
        if not isinstance(item, dict):
            continue
        term = _apify_term(item)
        channel = channel_from_term(term) if term else None
        organic = item.get("organicResults") or item.get("organic_results")
        if isinstance(organic, list):
            if channel:
                grouped[channel].extend(hits_from_items(channel, organic))
            continue
        url = item.get("url") or item.get("link")
        title = item.get("title")
        if channel and url and title:
            grouped[channel].extend(hits_from_items(channel, [item]))
    return {channel: _trim(hits) for channel, hits in grouped.items()}


def _apify_term(item: dict) -> str:
    raw = item.get("searchQuery")
    if isinstance(raw, dict):
        return str(raw.get("term") or "")
    if isinstance(raw, str):
        return raw
    return ""


def grounding_hits(payload: dict, channel: str) -> list[ChannelHit]:
    candidates = payload.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return []
    meta = candidates[0].get("groundingMetadata") or candidates[0].get("grounding_metadata") or {}
    chunks = meta.get("groundingChunks") or meta.get("grounding_chunks") or []
    items: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web") or {}
        if not isinstance(web, dict):
            continue
        url = public_http_url(str(web.get("uri") or web.get("url") or ""))
        title = clean_title(str(web.get("title") or ""))
        if not url or not title or not _accept_grounded_url(channel, url):
            continue
        items.append({"title": title, "url": url, "position": index, "snippet": ""})
    return hits_from_items(channel, items) if channel == "google" else _trim(
        [
            ChannelHit(rank=int(item["position"]), title=str(item["title"]), url=str(item["url"]), snippet="")
            for item in items
        ]
    )


def _accept_grounded_url(channel: str, url: str) -> bool:
    if channel == "google":
        return True
    if "grounding-api-redirect" in url or hostname(url) in GROUNDING_HOSTS:
        return True
    return is_channel_post(channel, url)


def overall_status(channels: list[ChannelOutcome]) -> str:
    modes = {channel.mode for channel in channels}
    if modes == {"not_configured"}:
        return "not_configured"
    if all(channel.mode == "live" for channel in channels):
        return "completed"
    if any(channel.hits for channel in channels) or "live" in modes:
        return "partial"
    return "failed"


def normalize_channels(channels: list[ChannelOutcome], *, provider: str) -> list[ChannelOutcome]:
    by_name = {channel.channel: channel for channel in channels}
    normalized: list[ChannelOutcome] = []
    for name in CHANNELS:
        normalized.append(
            by_name.get(name)
            or ChannelOutcome(channel=name, mode="failed", provider=provider, reason="This channel was not searched.", hits=[])
        )
    return normalized


class UnconfiguredChannelSearch:
    def search(self, query: str) -> ChannelSearchOutcome:
        _ = query
        channels = [
            ChannelOutcome(
                channel=name,
                mode="not_configured",
                provider="not_configured",
                reason=NOT_CONFIGURED_DETAIL,
                hits=[],
            )
            for name in CHANNELS
        ]
        return ChannelSearchOutcome(provider="not_configured", channels=channels)


class GoogleCseChannelSearch:
    def __init__(self, api_key: str, cx: str, client: Any = None) -> None:
        self._api_key = api_key
        self._cx = cx
        self._client = client

    def search(self, query: str) -> ChannelSearchOutcome:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        channels: list[ChannelOutcome] = []
        try:
            for name in CHANNELS:
                channels.append(self._one(client, name, query))
        finally:
            if owns_client:
                client.close()
        return ChannelSearchOutcome(provider="google_cse", channels=channels)

    def _one(self, client: Any, channel: str, query: str) -> ChannelOutcome:
        try:
            response = client.get(
                CSE_URL,
                params={"key": self._api_key, "cx": self._cx, "q": channel_query(channel, query), "num": RESULT_LIMIT},
            )
        except httpx.HTTPError:
            return ChannelOutcome(channel, "failed", "google_cse", "Google search could not be reached.", [])
        status = getattr(response, "status_code", 200)
        payload = _json_dict(response)
        if status >= 400:
            message = ""
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or "")
            reason = _redact(message or f"Google search refused ({status}).", self._api_key, self._cx)
            return ChannelOutcome(channel, "failed", "google_cse", reason, [])
        hits = relevant_hits(query, hits_from_items(channel, payload.get("items") or []))
        reason = "" if hits else NO_MATCH_REASON
        return ChannelOutcome(channel, "live", "google_cse", reason, hits)


class ApifyChannelSearch:
    def __init__(self, token: str, actor_id: str, client: Any = None) -> None:
        self._token = token
        self._actor_id = actor_id.strip().replace("/", "~")
        self._client = client

    def search(self, query: str) -> ChannelSearchOutcome:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=150.0)
        try:
            grouped, reason, mode = self._run(client, query)
        finally:
            if owns_client:
                client.close()
        if mode == "live":
            grouped = {name: relevant_hits(query, hits) for name, hits in grouped.items()}
            reason = NO_MATCH_REASON
        channels = [
            ChannelOutcome(
                channel=name,
                mode=mode,
                provider="apify",
                reason="" if grouped[name] else reason or NO_MATCH_REASON,
                hits=grouped[name],
            )
            for name in CHANNELS
        ]
        return ChannelSearchOutcome(provider="apify", channels=channels)

    def _run(self, client: Any, query: str) -> tuple[dict[str, list[ChannelHit]], str, str]:
        empty = {name: [] for name in CHANNELS}
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        try:
            start = client.post(
                f"https://api.apify.com/v2/acts/{self._actor_id}/runs",
                headers=headers,
                json={
                    "queries": search_queries(query),
                    "maxPagesPerQuery": 1,
                    "saveHtml": False,
                    "saveHtmlToKeyValueStore": False,
                },
                params={"waitForFinish": 90},
            )
        except httpx.HTTPError:
            return empty, "Apify search could not be reached. No posts were invented.", "failed"
        if getattr(start, "status_code", 200) >= 400:
            return empty, _redact(f"Apify search refused ({start.status_code}). No posts were invented.", self._token), "failed"
        body = _json_dict(start).get("data") or {}
        if not isinstance(body, dict):
            body = {}
        dataset_id, status, message = _apify_run_state(body)
        if status not in {"SUCCEEDED", "READY"} or not dataset_id:
            try:
                wait = client.get(
                    f"https://api.apify.com/v2/actor-runs/{body.get('id')}",
                    headers=headers,
                    params={"waitForFinish": 90},
                )
            except httpx.HTTPError:
                return empty, "Apify search could not be reached. No posts were invented.", "failed"
            if getattr(wait, "status_code", 200) >= 400:
                return empty, "Apify search did not finish. No posts were invented.", "failed"
            waited = _json_dict(wait).get("data") or {}
            if isinstance(waited, dict):
                dataset_id, status, message = _apify_run_state(waited)
        if status != "SUCCEEDED" or not dataset_id:
            detail = f" {message}" if message else ""
            return empty, _redact(f"Apify search ended {status or 'unknown'}.{detail} No posts were invented.", self._token), "failed"
        try:
            items = client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                headers=headers,
                params={"limit": 80},
            )
        except httpx.HTTPError:
            return empty, "Apify results could not be read. No posts were invented.", "failed"
        if getattr(items, "status_code", 200) >= 400:
            return empty, "Apify results could not be read. No posts were invented.", "failed"
        rows = items.json() if hasattr(items, "json") else []
        if not isinstance(rows, list):
            return empty, "Apify results were not a list. No posts were invented.", "failed"
        return parse_apify_items(rows), "No public posts were returned for this keyword.", "live"


class GeminiChannelSearch:
    def __init__(self, api_key: str, model: str, client: Any = None) -> None:
        self._api_key = api_key
        self._model = model.strip().removeprefix("models/")
        self._client = client

    def search(self, query: str) -> ChannelSearchOutcome:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=60.0)
        channels: list[ChannelOutcome] = []
        try:
            for name in CHANNELS:
                channels.append(self._one(client, name, query))
        finally:
            if owns_client:
                client.close()
        return ChannelSearchOutcome(provider="gemini", channels=channels)

    def _one(self, client: Any, channel: str, query: str) -> ChannelOutcome:
        try:
            response = client.post(
                f"{GEMINI_API_BASE}/models/{self._model}:generateContent",
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": f"Search Google for public pages matching: {channel_query(channel, query)}"}]}],
                    "tools": [{"google_search": {}}],
                },
            )
        except httpx.HTTPError:
            return ChannelOutcome(channel, "failed", "gemini", "Google Search could not be reached. No posts were invented.", [])
        status = getattr(response, "status_code", 200)
        payload = _json_dict(response)
        if status >= 400:
            message = ""
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or "")
            reason = _redact(message or f"Google Search refused ({status}). No posts were invented.", self._api_key)
            return ChannelOutcome(channel, "failed", "gemini", reason, [])
        hits = relevant_hits(query, grounding_hits(payload, channel))
        reason = "" if hits else NO_MATCH_REASON
        return ChannelOutcome(channel, "live", "gemini", reason, hits)


def _json_dict(response: Any) -> dict:
    reader = getattr(response, "json", None)
    payload = reader() if callable(reader) else {}
    return payload if isinstance(payload, dict) else {}


def _apify_run_state(body: dict) -> tuple[str, str, str]:
    dataset_id = str(body.get("defaultDatasetId") or "")
    status = str(body.get("status") or "")
    message = str(body.get("statusMessage") or "")
    return dataset_id, status, message


def get_channel_search_provider() -> UnconfiguredChannelSearch | GoogleCseChannelSearch | ApifyChannelSearch | GeminiChannelSearch:
    settings = get_settings()
    kind = settings.resolved_channel_search_provider
    if kind == "google_cse":
        return GoogleCseChannelSearch(settings.google_cse_api_key.strip(), settings.google_cse_cx.strip())
    if kind == "apify":
        return ApifyChannelSearch(settings.resolved_apify_token.strip(), settings.channel_search_apify_actor.strip())
    if kind == "gemini":
        model = settings.gemini_default_model or settings.gemini_fast_model
        return GeminiChannelSearch(settings.gemini_api_key.strip(), model.strip())
    return UnconfiguredChannelSearch()
