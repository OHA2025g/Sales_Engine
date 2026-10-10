import json

from app.providers.email import GmailEmailProvider


class Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


def test_missing_history_falls_back_to_inbox() -> None:
    calls: list[str] = []

    def getter(url: str, **_kwargs):
        calls.append(url)
        if url.endswith("/messages/abc"):
            return Response(
                200,
                {
                    "id": "abc",
                    "threadId": "thread-1",
                    "historyId": "99",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "lead@example.com"},
                            {"name": "To", "value": "seller@example.com"},
                            {"name": "Subject", "value": "Re: Follow-up"},
                        ],
                        "body": {"data": ""},
                    },
                },
            )
        if url.endswith("/messages"):
            return Response(200, {"messages": [{"id": "abc"}]})
        return Response(400, {"error": "startHistoryId required"})

    rows = GmailEmailProvider(access_token="token", http_get=getter).list_since(history_id="")
    assert [row.provider_message_id for row in rows] == ["abc"]
    assert rows[0].subject == "Re: Follow-up"
    assert not any(url.endswith("/history") for url in calls)


def test_stale_history_falls_back_to_inbox() -> None:
    def getter(url: str, **_kwargs):
        if url.endswith("/history"):
            return Response(404, {"error": "not found"})
        if url.endswith("/messages/abc"):
            return Response(
                200,
                {
                    "id": "abc",
                    "threadId": "thread-1",
                    "historyId": "100",
                    "payload": {"headers": [{"name": "Subject", "value": "Re: Follow-up"}], "body": {"data": ""}},
                },
            )
        return Response(200, {"messages": [{"id": "abc"}]})

    rows = GmailEmailProvider(access_token="token", http_get=getter).list_since(history_id="stale")
    assert [row.provider_message_id for row in rows] == ["abc"]
