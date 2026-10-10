from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_credential, encrypt_credential
from app.db.tenant_context import set_form_token_hash
from app.models.funnel import PublicFormKey
from app.services.audit import write_audit


def hash_form_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_form_key(db: Session, *, tenant_id: UUID, actor_id: UUID, name: str = "website") -> tuple[PublicFormKey, str]:
    raw = secrets.token_urlsafe(32)
    row = PublicFormKey(
        tenant_id=tenant_id,
        created_by=actor_id,
        name=name.strip() or "website",
        token_hash=hash_form_token(raw),
        status="active",
        token_encrypted=encrypt_credential(raw),
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="public_form.create",
        entity_type="public_form_key",
        entity_id=str(row.id),
        after={"name": row.name},
    )
    return row, raw


def resolve_form_key(db: Session, raw_token: str) -> PublicFormKey:
    hashed = hash_form_token(raw_token)
    set_form_token_hash(db, hashed)
    row = db.scalar(
        select(PublicFormKey).where(
            PublicFormKey.token_hash == hashed,
            PublicFormKey.status == "active",
            PublicFormKey.deleted_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown public form key")
    row.last_used_at = datetime.now(UTC)
    return row


def list_form_keys(db: Session, tenant_id: UUID) -> list[PublicFormKey]:
    return list(
        db.scalars(
            select(PublicFormKey).where(PublicFormKey.tenant_id == tenant_id, PublicFormKey.deleted_at.is_(None)).order_by(PublicFormKey.created_at.desc())
        )
    )


def revoke_form_key(db: Session, row: PublicFormKey) -> PublicFormKey:
    row.status = "revoked"
    return row


INTEREST_FORM_NAME = "Interest form"


def ensure_interest_form(db: Session, *, tenant_id: UUID, actor_id: UUID) -> str:
    row = db.scalar(
        select(PublicFormKey)
        .where(
            PublicFormKey.tenant_id == tenant_id,
            PublicFormKey.name == INTEREST_FORM_NAME,
            PublicFormKey.status == "active",
            PublicFormKey.deleted_at.is_(None),
            PublicFormKey.token_encrypted != "",
        )
        .order_by(PublicFormKey.created_at.desc())
    )
    if row is not None:
        return decrypt_credential(row.token_encrypted)
    _created, raw = create_form_key(db, tenant_id=tenant_id, actor_id=actor_id, name=INTEREST_FORM_NAME)
    return raw


def interest_form_url(token: str) -> str:
    origin = get_settings().web_app_origin.strip().rstrip("/") or "http://localhost:3000"
    return f"{origin}/capture/{token}"


def form_key_url(row: PublicFormKey) -> str:
    if row.status != "active" or not row.token_encrypted:
        return ""
    try:
        token = decrypt_credential(row.token_encrypted)
    except ValueError:
        return ""
    if not token:
        return ""
    return interest_form_url(token)


def social_form_link(row: PublicFormKey, channel: str) -> str:
    base = form_key_url(row)
    if not base:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This form has no public link.")
    query = urlencode(
        {
            "source": "social_post",
            "channel": channel,
            "utm_source": channel,
            "utm_medium": "social",
            "utm_campaign": row.name.strip().replace(" ", "-")[:80],
        }
    )
    link = f"{base}?{query}"
    if len(link) > 500:
        link = base
    if len(link) > 500:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The form link is too long to attach.")
    return link


def active_form_name_taken(db: Session, tenant_id: UUID, name: str) -> bool:
    row = db.scalar(
        select(PublicFormKey.id).where(
            PublicFormKey.tenant_id == tenant_id,
            PublicFormKey.name == name,
            PublicFormKey.status == "active",
            PublicFormKey.deleted_at.is_(None),
        )
    )
    return row is not None
