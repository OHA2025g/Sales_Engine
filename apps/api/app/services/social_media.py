from __future__ import annotations

import secrets
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_credential
from app.db.tenant_context import set_form_token_hash
from app.models.social import SocialImage
from app.providers.object_storage import get_object_storage
from app.services.audit import write_audit
from app.services.public_forms import hash_form_token

MAX_IMAGE_BYTES = 8 * 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"


def image_kind(data: bytes) -> str | None:
    if data.startswith(_PNG):
        return "image/png"
    if data.startswith(_JPEG):
        return "image/jpeg"
    return None


def store_social_image(db: Session, *, tenant_id: UUID, actor_id: UUID, data: bytes) -> str:
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 8 MB or smaller.")
    kind = image_kind(data)
    if kind is None:
        raise HTTPException(status_code=422, detail="Upload a JPEG or PNG.")
    image_id = uuid4()
    key = f"tenant/{tenant_id}/social/{image_id}"
    get_object_storage().put(key, data, content_type=kind)
    raw = secrets.token_urlsafe(32)
    row = SocialImage(
        id=image_id,
        tenant_id=tenant_id,
        created_by=actor_id,
        object_key=key,
        content_type=kind,
        token_hash=hash_form_token(raw),
        token_encrypted=encrypt_credential(raw),
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="social.image_upload",
        entity_type="social_image",
        entity_id=str(row.id),
        after={"content_type": kind, "bytes": len(data)},
    )
    base = get_settings().public_api_base_url.rstrip("/") or "http://localhost:8000"
    return f"{base}/api/v1/public/media/{raw}"


def read_social_image(db: Session, raw_token: str) -> tuple[bytes, str]:
    hashed = hash_form_token(raw_token)
    set_form_token_hash(db, hashed)
    row = db.scalar(select(SocialImage).where(SocialImage.token_hash == hashed, SocialImage.deleted_at.is_(None)))
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        data = get_object_storage().get(row.object_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc
    return data, row.content_type
