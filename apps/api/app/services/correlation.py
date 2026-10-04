import hashlib


def bound_correlation_id(value: str) -> str:
    text = (value or "").strip()
    if len(text) <= 64:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{text[:47]}:{digest}"
