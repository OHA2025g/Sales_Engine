import json

import httpx

from app.providers.voice import VoiceHealth, VoiceSession
from app.providers.voice_conversation import DograhConversationProvider
from app.services.provider_resolve import ResolvedProvider
from app.services.voice_router import VoiceRouter, _conversation_from_resolved


class _Carrier:
    def __init__(self) -> None:
        self.dials = 0

    def health(self) -> VoiceHealth:
        return VoiceHealth(provider="twilio", is_mock=True, connected=False, reason="unused")

    def dial(self, **kwargs) -> VoiceSession:
        _ = kwargs
        self.dials += 1
        return VoiceSession(ok=True, session_id="carrier-should-not-run", provider="twilio", is_mock=True)


def test_dograh_places_the_call_and_skips_the_carrier() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("X-API-Key")
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "initiated", "workflow_run_id": 42, "workflow_run_name": "sales"})

    conversation = DograhConversationProvider(
        api_key="dograh-key",
        agent_uuid="agent-1",
        api_base="http://dograh.local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    carrier = _Carrier()
    router = VoiceRouter(
        telephony=carrier,
        conversation=conversation,
        carrier="twilio",
        conversation_name="dograh",
        region="INTL",
        script="Ask about the renewal date.",
    )
    session = router.start_session(to_number="+15551230000", from_label="AGRAYIAN")
    assert session.ok is True
    assert session.provider == "dograh"
    assert session.session_id == "42"
    assert session.call_status == "QUEUED"
    assert carrier.dials == 0
    assert seen["path"] == "/api/v1/public/agent/agent-1"
    assert seen["key"] == "dograh-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["phone_number"] == "+15551230000"
    assert body["initial_context"]["sales_script"] == "Ask about the renewal date."


def test_missing_dograh_credentials_do_not_dial() -> None:
    provider = _conversation_from_resolved("dograh", ResolvedProvider("NOT_CONFIGURED", "dograh", None, "missing", False, {}))
    session = provider.attach(session_id="", to_number="+15551230000", script="Hello")
    assert session.ok is False
    assert session.provider == "dograh"
    assert session.is_mock is False
