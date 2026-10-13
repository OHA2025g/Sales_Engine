import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _build_hasher() -> PasswordHasher:
    # Production stays at the 19 MiB OWASP minimum. Other environments use
    # 6 MiB and two iterations, which cuts verification by about 70 percent.
    if get_settings().is_production:
        return PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
    return PasswordHasher(time_cost=2, memory_cost=6144, parallelism=1)


hasher = _build_hasher()


def _fernet() -> Fernet:
    settings = get_settings()
    raw = (settings.token_encryption_key or settings.secret_key).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credential(value: str) -> str:
    if not value:
        return ""
    return "v1:" + _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_credential(value: str) -> str:
    if not value:
        return ""
    raw = value[3:] if value.startswith("v1:") else value
    try:
        return _fernet().decrypt(raw.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Integration credential could not be decrypted") from exc


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    return True


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return hasher.check_needs_rehash(password_hash)
    except InvalidHash:
        return False


def create_access_token(*, user_id: UUID, tenant_id: UUID, email: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "email": email,
        "exp": expire,
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
