from app.core.config import get_settings
from app.schemas.lifecycle import DograhBrowserTestOut
from app.services.dograh_browser import browser_test_from_settings, build_dograh_browser_test


def test_embed_token_builds_a_widget_url_without_the_api_key() -> None:
    result = build_dograh_browser_test(
        api_base="https://dograh.example",
        ui_base="https://dograh-ui.example",
        voice_token="voice-token",
        chat_token="chat-token",
        voice_widget_src="",
        chat_widget_src="",
        sales_script="Ask about the renewal date.",
    )
    assert result.ready is True
    assert "dograh-key" not in result.voice_widget_src
    assert "dograh-key" not in result.chat_widget_src
    assert result.voice_widget_src.startswith("https://dograh-ui.example/embed/dograh-widget.js?")
    assert "token=voice-token" in result.voice_widget_src
    assert "token=chat-token" in result.chat_widget_src
    assert "apiEndpoint=https%3A%2F%2Fdograh.example" in result.chat_widget_src
    assert result.sales_script == "Ask about the renewal date."
    payload = DograhBrowserTestOut.model_validate(result, from_attributes=True)
    assert payload.chat_widget_src == result.chat_widget_src


def test_explicit_widget_url_is_kept_and_a_phone_script_url_is_rejected() -> None:
    kept = build_dograh_browser_test(
        api_base="https://dograh.example",
        ui_base="",
        voice_token="",
        chat_token="",
        voice_widget_src="https://dograh-ui.example/embed/dograh-widget.js?token=abc&environment=production",
        chat_widget_src="javascript:alert(1)",
        sales_script="x" * 2500,
    )
    assert kept.voice_widget_src.endswith("environment=production")
    assert kept.chat_widget_src == ""
    assert kept.ready is True
    assert len(kept.sales_script) == 2000


def test_missing_token_is_not_ready() -> None:
    result = build_dograh_browser_test(
        api_base="https://dograh.example",
        ui_base="",
        voice_token="",
        chat_token="",
        voice_widget_src="",
        chat_widget_src="",
        sales_script="",
    )
    assert result.ready is False
    assert result.voice_widget_src == ""
    assert "API key" in result.reason


def test_environment_is_included_in_built_widget_url() -> None:
    result = build_dograh_browser_test(
        api_base="http://localhost:8003",
        ui_base="http://localhost:3010",
        voice_token="emb-token",
        chat_token="",
        voice_widget_src="",
        chat_widget_src="",
        sales_script="",
        environment="local",
    )
    assert "environment=local" in result.voice_widget_src
    assert "apiEndpoint=http%3A%2F%2Flocalhost%3A8003" in result.voice_widget_src
    assert "token=emb-token" in result.chat_widget_src
    assert result.chat_widget_src.startswith("http://localhost:3010/embed/dograh-widget.js?")


def test_settings_read_the_chat_token(monkeypatch) -> None:
    monkeypatch.setenv("DOGRAH_CHAT_EMBED_TOKEN", "chat-from-env")
    monkeypatch.setenv("DOGRAH_API_BASE", "https://dograh.example")
    monkeypatch.setenv("DOGRAH_UI_BASE", "")
    monkeypatch.setenv("DOGRAH_EMBED_TOKEN", "")
    monkeypatch.setenv("DOGRAH_VOICE_WIDGET_SRC", "")
    monkeypatch.setenv("DOGRAH_CHAT_WIDGET_SRC", "")
    get_settings.cache_clear()
    try:
        result = browser_test_from_settings(sales_script="")
    finally:
        get_settings.cache_clear()
    assert result.ready is True
    assert result.voice_widget_src == ""
    assert result.chat_widget_src.startswith("https://dograh.example/embed/dograh-widget.js?")
    assert "token=chat-from-env" in result.chat_widget_src
