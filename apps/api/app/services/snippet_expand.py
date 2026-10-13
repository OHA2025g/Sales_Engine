import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.channel_search import ChannelSearchHit
from app.providers.channel_search import public_http_url

_PAGE_LIMIT = 400_000
_TEXT_LIMIT = 1600
_USER_AGENT = "Mozilla/5.0 (compatible; SalesEngine/1.0; +https://agrayianailabs.com)"


class SnippetNotFound(Exception):
    pass


class SnippetUnavailable(Exception):
    pass


class _PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta = ""
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag != "meta":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        name = (values.get("property") or values.get("name") or "").lower()
        if name in {"description", "og:description"} and not self.meta:
            self.meta = values.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "br", "div"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def _needle(snippet: str) -> str:
    cleaned = snippet
    marker = cleaned.lower().rfind("read more")
    if marker >= 0:
        cleaned = cleaned[:marker]
    cleaned = cleaned.replace("…", " ").replace("...", " ")
    words = cleaned.split()
    return " ".join(words[:12])


def _trim(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _TEXT_LIMIT:
        return collapsed
    chunk = collapsed[:_TEXT_LIMIT]
    stop = chunk.rfind(". ")
    if stop > 400:
        return chunk[: stop + 1]
    return chunk


def choose_detail(stored: str, meta: str, body: str) -> str:
    folded = " ".join(body.split())
    needle = _needle(stored)
    if needle:
        index = folded.lower().find(needle.lower())
        if index >= 0:
            detail = _trim(folded[index:])
            if len(detail) > len(stored) + 40:
                return detail
    description = _trim(meta)
    if len(description) > len(stored) + 40:
        return description
    if len(folded) > len(stored) + 80:
        return _trim(folded)
    raise SnippetUnavailable("The page did not include a longer description.")


def _addresses(host: str) -> list[str]:
    try:
        return [item[4][0] for item in socket.getaddrinfo(host, None)]
    except socket.gaierror as exc:
        raise SnippetUnavailable("The page could not be reached.") from exc


def assert_public_url(url: str) -> str:
    cleaned = public_http_url(url)
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if not cleaned or parsed.username or parsed.password or not host or host.endswith(".local"):
        raise SnippetUnavailable("That address cannot be read.")
    for address in _addresses(host):
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise SnippetUnavailable("That address cannot be read.") from exc
        if not ip.is_global:
            raise SnippetUnavailable("That address cannot be read.")
    return cleaned


def fetch_page_html(url: str, client: httpx.Client | None = None) -> str:
    owns_client = client is None
    http = client or httpx.Client(timeout=12.0)
    current = url
    try:
        for _ in range(4):
            current = assert_public_url(current)
            try:
                response = http.get(
                    current,
                    headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise SnippetUnavailable("The page could not be reached.") from exc
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location") or ""
                if not location:
                    raise SnippetUnavailable("The page could not be reached.")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise SnippetUnavailable("The page could not be reached.")
            content_type = response.headers.get("content-type", "")
            if content_type and "html" not in content_type and "text/plain" not in content_type:
                raise SnippetUnavailable("The page did not include a longer description.")
            return response.text[:_PAGE_LIMIT]
        raise SnippetUnavailable("The page could not be reached.")
    finally:
        if owns_client:
            http.close()


def html_text(html: str) -> tuple[str, str]:
    parser = _PageText()
    parser.feed(html)
    parser.close()
    return parser.meta, "".join(parser.parts)


def expand_snippet(db: Session, tenant_id: UUID, url: str, client: httpx.Client | None = None) -> str:
    cleaned = public_http_url(url)
    if not cleaned:
        raise SnippetUnavailable("That address cannot be read.")
    hit = db.scalar(
        select(ChannelSearchHit).where(
            ChannelSearchHit.tenant_id == tenant_id,
            ChannelSearchHit.url == cleaned,
            ChannelSearchHit.deleted_at.is_(None),
        )
    )
    if hit is None:
        raise SnippetNotFound("That result was not found.")
    meta, body = html_text(fetch_page_html(cleaned, client))
    return choose_detail(hit.snippet, meta, body)
