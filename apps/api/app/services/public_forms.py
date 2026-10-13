from __future__ import annotations

import hashlib
import html
import json
import re
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


_MAPPED_KEYS = {"first_name", "last_name", "email", "phone", "company_name", "title", "request_note", "consent_email"}
_FIELD_TYPES = {"text", "email", "tel", "textarea", "checkbox", "select"}
_CUSTOM_KEY = re.compile(r"^custom_[a-z0-9]{1,24}$")


def default_form_fields() -> list[dict]:
    return [
        {"key": "first_name", "label": "First name", "type": "text", "required": True, "placeholder": "", "options": []},
        {"key": "last_name", "label": "Last name", "type": "text", "required": True, "placeholder": "", "options": []},
        {"key": "email", "label": "Work email", "type": "email", "required": True, "placeholder": "", "options": []},
        {"key": "phone", "label": "Phone", "type": "tel", "required": False, "placeholder": "", "options": []},
        {"key": "company_name", "label": "Company", "type": "text", "required": False, "placeholder": "", "options": []},
        {"key": "title", "label": "Role", "type": "text", "required": False, "placeholder": "", "options": []},
        {"key": "request_note", "label": "What do you want?", "type": "textarea", "required": True, "placeholder": "Describe what you want next.", "options": []},
        {"key": "consent_email", "label": "I agree to be contacted about this request.", "type": "checkbox", "required": True, "placeholder": "", "options": []},
    ]


def normalize_form_fields(raw: list[dict]) -> list[dict]:
    if not raw:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add at least one field.")
    if len(raw) > 16:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A form can have up to 16 fields.")
    seen: set[str] = set()
    fields: list[dict] = []
    for item in raw:
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or "").strip()
        kind = str(item.get("type") or "").strip()
        if key in _MAPPED_KEYS:
            if key in seen:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Each lead field can be added once.")
            seen.add(key)
        elif not _CUSTOM_KEY.fullmatch(key):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A field key is not recognized.")
        if not label or len(label) > 120:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Each field needs a label.")
        if kind not in _FIELD_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A field type is not recognized.")
        if key == "consent_email" and kind != "checkbox":
            kind = "checkbox"
        if key == "email":
            kind = "email"
        if key == "request_note":
            kind = "textarea"
        options = [str(option).strip() for option in (item.get("options") or []) if str(option).strip()]
        if kind == "select" and not options:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A choice list needs at least one option.")
        if kind != "select":
            options = []
        fields.append(
            {
                "key": key,
                "label": label,
                "type": kind,
                "required": bool(item.get("required")),
                "placeholder": "" if kind == "checkbox" else str(item.get("placeholder") or "").strip()[:160],
                "options": options[:12],
            }
        )
    return fields


def dumps_form_fields(fields: list[dict]) -> str:
    return json.dumps(fields, separators=(",", ":"))


def loads_form_fields(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if not text:
        return default_form_fields()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return default_form_fields()
    if not isinstance(parsed, list):
        return default_form_fields()
    try:
        return normalize_form_fields([item for item in parsed if isinstance(item, dict)])
    except HTTPException:
        return default_form_fields()


def public_form_inputs(fields: list[dict]) -> tuple[str, dict[str, str]]:
    parts: list[str] = []
    labels: dict[str, str] = {}
    for field in fields:
        key = html.escape(field["key"], quote=True)
        label = html.escape(field["label"])
        required = " required" if field["required"] else ""
        placeholder = html.escape(field["placeholder"], quote=True)
        labels[field["key"]] = field["label"]
        kind = field["type"]
        if kind == "checkbox":
            parts.append(f'<label class="check"><input type="checkbox" name="{key}" value="true"{required}> {label}</label>')
            continue
        if kind == "textarea":
            parts.append(f'<label>{label}<textarea name="{key}" rows="5" placeholder="{placeholder}"{required}></textarea></label>')
            continue
        if kind == "select":
            options = "".join(f'<option value="{html.escape(option, quote=True)}">{html.escape(option)}</option>' for option in field["options"])
            parts.append(f'<label>{label}<select name="{key}"{required}><option value="">Select</option>{options}</select></label>')
            continue
        input_type = kind if kind in {"email", "tel"} else "text"
        parts.append(f'<label>{label}<input name="{key}" type="{input_type}" placeholder="{placeholder}"{required}></label>')
    return "".join(parts), labels


def create_form_key(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    name: str = "website",
    fields: list[dict] | None = None,
) -> tuple[PublicFormKey, str]:
    raw = secrets.token_urlsafe(32)
    row = PublicFormKey(
        tenant_id=tenant_id,
        created_by=actor_id,
        name=name.strip() or "website",
        schema_json=dumps_form_fields(normalize_form_fields(fields)) if fields else "",
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


def update_form_design(db: Session, row: PublicFormKey, *, name: str, fields: list[dict]) -> PublicFormKey:
    label = name.strip()
    if not label:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name the form.")
    if len(label) > 120:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Form name is too long.")
    row.name = label
    row.schema_json = dumps_form_fields(normalize_form_fields(fields))
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


def active_form_name_taken(db: Session, tenant_id: UUID, name: str, exclude_id: UUID | None = None) -> bool:
    query = select(PublicFormKey.id).where(
        PublicFormKey.tenant_id == tenant_id,
        PublicFormKey.name == name,
        PublicFormKey.status == "active",
        PublicFormKey.deleted_at.is_(None),
    )
    if exclude_id is not None:
        query = query.where(PublicFormKey.id != exclude_id)
    return db.scalar(query) is not None
