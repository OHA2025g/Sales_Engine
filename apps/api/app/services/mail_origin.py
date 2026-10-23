"""Separate people from automated mail before a sales response is sent."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import EmailMessage

MessageOrigin = Literal["human", "automated", "out_of_office", "bounce", "self"]

AUTOMATED_WINDOW = timedelta(hours=1)
LOOP_LIMIT = 2
HEADER_NAMES = ("auto-submitted", "precedence", "x-auto-response-suppress", "x-autoreply", "x-autorespond")
_BOUNCE_LOCALS = {"mailer-daemon", "postmaster", "mail-daemon"}
_AUTOMATED_LOCALS = {"noreply", "no-reply", "donotreply", "do-not-reply", "notifications", "notification"}


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def _address(value: str) -> str:
    text = (value or "").strip().casefold()
    if "<" in text and ">" in text:
        text = text.split("<", 1)[1].split(">", 1)[0].strip()
    return text


def kept_headers(headers: dict | None) -> dict[str, str]:
    kept: dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key or "").strip().casefold()
        if name in HEADER_NAMES:
            kept[name] = str(value or "")[:300]
    return kept


def message_origin(
    *,
    from_addr: str,
    subject: str,
    body: str,
    mailbox: str = "",
    headers: dict | None = None,
) -> MessageOrigin:
    sender = _address(from_addr)
    own = _address(mailbox)
    if own and sender == own:
        return "self"
    folded = {str(key).casefold(): str(value or "").casefold() for key, value in (headers or {}).items()}
    text = f"{subject}\n{body}".casefold()
    local = sender.split("@", 1)[0]
    if local in _BOUNCE_LOCALS or any(
        token in text
        for token in ("undeliverable", "delivery status notification", "mail delivery failed", "returned mail", "delivery failure")
    ):
        return "bounce"
    if any(token in text for token in ("out of office", "out-of-office", "on leave", "parental leave", "away from the office")):
        return "out_of_office"
    auto_submitted = folded.get("auto-submitted", "")
    precedence = folded.get("precedence", "")
    automated = bool(auto_submitted and auto_submitted not in {"no", "none"})
    automated = automated or precedence in {"bulk", "junk", "auto_reply", "list"}
    automated = automated or local in _AUTOMATED_LOCALS or local.startswith("noreply") or local.startswith("no-reply")
    automated = automated or any(
        token in text
        for token in (
            "this is an automated",
            "this is an automatic",
            "automatic reply",
            "auto-reply",
            "autoreply",
            "do not reply",
            "please do not reply",
        )
    )
    if automated:
        return "automated"
    return "human"


def headers_of(message: EmailMessage) -> dict:
    try:
        loaded = json.loads(message.header_json or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def automated_inbound_count(db: Session, *, tenant_id: UUID, conversation_id: UUID, now: datetime | None = None) -> int:
    moment = now or datetime.now(UTC)
    since = moment - AUTOMATED_WINDOW
    rows = db.scalars(
        select(EmailMessage).where(
            EmailMessage.tenant_id == tenant_id,
            EmailMessage.conversation_id == conversation_id,
            EmailMessage.direction == "inbound",
            EmailMessage.deleted_at.is_(None),
        )
    ).all()
    count = 0
    for row in rows:
        received = _aware(row.received_at or row.created_at)
        if received is None or received < since:
            continue
        origin = message_origin(
            from_addr=row.from_addr,
            subject=row.subject,
            body=row.body_text,
            headers=headers_of(row),
        )
        if origin in {"automated", "bounce"}:
            count += 1
    return count


def response_block(db: Session, *, tenant_id: UUID, thread_id: str) -> str:
    """Refuse a send that would answer automated mail or continue a loop."""
    if not thread_id.strip():
        return ""
    latest = db.scalar(
        select(EmailMessage)
        .where(
            EmailMessage.tenant_id == tenant_id,
            EmailMessage.provider_thread_id == thread_id,
            EmailMessage.direction == "inbound",
            EmailMessage.deleted_at.is_(None),
        )
        .order_by(EmailMessage.created_at.desc())
    )
    if latest is None:
        return ""
    origin = message_origin(
        from_addr=latest.from_addr,
        subject=latest.subject,
        body=latest.body_text,
        headers=headers_of(latest),
    )
    if origin == "human":
        return ""
    if origin == "self":
        return "Send was not executed: the latest message is from the connected mailbox."
    if origin == "out_of_office":
        return "Send was not executed: the recipient is out of office."
    count = automated_inbound_count(db, tenant_id=tenant_id, conversation_id=latest.conversation_id)
    if count >= LOOP_LIMIT:
        return "Automated exchange stopped. The thread reached the response limit for this hour."
    if origin == "bounce":
        return "Send was not executed: delivery failed. No sales response is sent to a bounce."
    return "Send was not executed: no sales response is sent to an automated message."
