"""Browser test session for a Dograh agent.

Dograh's API key only starts a phone call. In-browser Test Audio and Test Chat
use the embed widget, which is identified by a token created in Configure Widget.
"""

from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from app.core.config import get_settings

_SCRIPT_LIMIT = 2000
_NOT_READY = "Dograh browser test needs an embed token from Configure Widget. The API key only places phone calls."
_READY = "Ready"


@dataclass(frozen=True)
class DograhBrowserTest:
    ready: bool
    reason: str
    voice_widget_src: str
    chat_widget_src: str
    sales_script: str


def build_dograh_browser_test(
    *,
    api_base: str,
    ui_base: str,
    voice_token: str,
    chat_token: str,
    voice_widget_src: str,
    chat_widget_src: str,
    sales_script: str,
) -> DograhBrowserTest:
    voice = resolve_widget_src(explicit=voice_widget_src, ui_base=ui_base, api_base=api_base, token=voice_token)
    chat = resolve_widget_src(explicit=chat_widget_src, ui_base=ui_base, api_base=api_base, token=chat_token)
    ready = bool(voice or chat)
    return DograhBrowserTest(
        ready=ready,
        reason=_READY if ready else _NOT_READY,
        voice_widget_src=voice,
        chat_widget_src=chat,
        sales_script=sales_script.strip()[:_SCRIPT_LIMIT],
    )


def browser_test_from_settings(*, sales_script: str) -> DograhBrowserTest:
    settings = get_settings()
    return build_dograh_browser_test(
        api_base=settings.dograh_api_base,
        ui_base=settings.dograh_ui_base,
        voice_token=settings.dograh_embed_token,
        chat_token=settings.dograh_chat_embed_token,
        voice_widget_src=settings.dograh_voice_widget_src,
        chat_widget_src=settings.dograh_chat_widget_src,
        sales_script=sales_script,
    )


def resolve_widget_src(*, explicit: str, ui_base: str, api_base: str, token: str) -> str:
    allowed = _allowed_widget_src(explicit)
    if allowed:
        return allowed
    return _built_widget_src(ui_base=ui_base, api_base=api_base, token=token)


def _allowed_widget_src(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    if "dograh-widget.js" not in parsed.path:
        return ""
    return raw


def _built_widget_src(*, ui_base: str, api_base: str, token: str) -> str:
    secret = token.strip()
    if not secret:
        return ""
    base = ui_base.strip().rstrip("/") or api_base.strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    params: dict[str, str] = {"token": secret}
    endpoint = api_base.strip().rstrip("/")
    if endpoint:
        params["apiEndpoint"] = endpoint
    return f"{base}/embed/dograh-widget.js?{urlencode(params)}"
