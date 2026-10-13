"""Write a post, a banner, and a short video from the new-post brief."""

from __future__ import annotations

import base64
import time
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.providers import GEMINI_API_BASE, get_llm_provider
from app.core.config import get_settings
from app.services.social_artwork import draw_banner_png, draw_title_clip
from app.services.social_media import store_social_gif, store_social_image, store_social_video

_IMAGE_MODELS = ("gemini-2.5-flash-image", "gemini-3.1-flash-lite-image", "gemini-3.1-flash-image")
_VIDEO_MODELS = ("veo-3.1-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.1-lite-generate-preview")
_BANNER_NOTE = "Gemini's plan cannot make an image right now, so this banner was drawn from the title. The keyword, ranking parameter, and snippet are not on it."
_CLIP_NOTE = "Gemini's plan cannot make a video right now, so this is a short moving clip of the title. The keyword, ranking parameter, and snippet are not on it."
_SYSTEM = (
    "You write one social post for a company. Use only the facts in the brief. "
    "Do not invent customers, numbers, or awards. "
    "Do not label the keyword, ranking parameter, or snippet. "
    "Write the post itself, with no preamble."
)


def _brief_lines(headline: str, keyword: str, ranking_parameter: str, snippet: str, context: str, body: str = "") -> str:
    lines = [
        f"Title: {headline.strip()}",
        f"Keyword, for direction only: {keyword.strip()}",
        f"Ranking parameter, for direction only: {ranking_parameter.strip()}",
        f"Snippet, for direction only: {snippet.strip()}",
        f"Context: {context.strip()}",
    ]
    if body.strip():
        lines.append(f"Descriptive post: {body.strip()}")
    return "\n".join(lines)


def _hidden_rule() -> str:
    return (
        "The keyword, ranking parameter, and snippet must not appear as written text. "
        "Use them only to decide the scene. The only words allowed on screen are the title, and only if they fit."
    )


def compose_post(
    db: Session,
    *,
    tenant_id: UUID,
    headline: str,
    keyword: str,
    ranking_parameter: str,
    snippet: str,
    context: str,
) -> str:
    _ = (db, tenant_id)
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini is not configured, so the post was not written.")
    result = get_llm_provider().complete(
        _brief_lines(headline, keyword, ranking_parameter, snippet, context),
        system=_SYSTEM,
    )
    text = result.text.strip()
    if not text or text.startswith("[NOT_CONFIGURED"):
        raise HTTPException(status_code=503, detail="Gemini is not configured, so the post was not written.")
    return text[:3000]


def _gemini_key() -> str:
    key = get_settings().gemini_api_key.strip()
    if not key:
        raise HTTPException(status_code=503, detail="Gemini is not configured, so this was not created.")
    return key


def _post(client: httpx.Client, url: str, key: str, body: dict) -> httpx.Response:
    return client.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body)


def _error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "").strip()
    return ""


def _image_bytes(payload: dict) -> tuple[bytes, str] | None:
    candidates = payload.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return None
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    for part in parts:
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData") or part.get("inline_data")
        if not isinstance(inline, dict):
            continue
        raw = inline.get("data")
        if not isinstance(raw, str) or not raw.strip():
            continue
        mime = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
        try:
            data = base64.b64decode(raw)
        except Exception:
            continue
        if data:
            return data, mime
    return None


def _quota(message: str) -> bool:
    text = message.lower()
    return "quota" in text or "rate limit" in text or "rate-limit" in text


def create_banner(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    headline: str,
    keyword: str,
    ranking_parameter: str,
    snippet: str,
    context: str,
    body: str,
) -> tuple[str, str]:
    key = _gemini_key()
    prompt = (
        "Create one wide social banner.\n"
        f"{_brief_lines(headline, keyword, ranking_parameter, snippet, context, body)}\n"
        f"{_hidden_rule()}"
    )
    with httpx.Client(timeout=90.0) as client:
        for model in _IMAGE_MODELS:
            response = _post(
                client,
                f"{GEMINI_API_BASE}/models/{model}:generateContent",
                key,
                {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
                },
            )
            if response.status_code >= 400:
                if _quota(_error_text(response)):
                    break
                continue
            found = _image_bytes(response.json())
            if found is None:
                continue
            data, _mime = found
            if not data.startswith(b"\x89PNG") and not data.startswith(b"\xff\xd8\xff"):
                continue
            return store_social_image(db, tenant_id=tenant_id, actor_id=actor_id, data=data), ""
    drawn = draw_banner_png(headline)
    return store_social_image(db, tenant_id=tenant_id, actor_id=actor_id, data=drawn), _BANNER_NOTE


def _video_uri(payload: dict) -> str:
    response = payload.get("response") or {}
    if not isinstance(response, dict):
        return ""
    generated = response.get("generateVideoResponse") or response.get("generate_video_response") or response
    samples = []
    if isinstance(generated, dict):
        samples = generated.get("generatedSamples") or generated.get("generated_samples") or generated.get("videos") or []
    if not isinstance(samples, list):
        return ""
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        video = sample.get("video") or sample
        if isinstance(video, dict):
            uri = str(video.get("uri") or video.get("url") or "")
            if uri.startswith("http"):
                return uri
    return ""


def create_short_video(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    headline: str,
    keyword: str,
    ranking_parameter: str,
    snippet: str,
    context: str,
    body: str,
) -> tuple[str, str]:
    key = _gemini_key()
    prompt = (
        "Create an 8 second silent social video.\n"
        f"{_brief_lines(headline, keyword, ranking_parameter, snippet, context, body)}\n"
        f"{_hidden_rule()}"
    )
    request = {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": "16:9", "durationSeconds": 8}}
    with httpx.Client(timeout=30.0) as client:
        operation = ""
        for model in _VIDEO_MODELS:
            response = _post(client, f"{GEMINI_API_BASE}/models/{model}:predictLongRunning", key, request)
            if response.status_code >= 400:
                if _quota(_error_text(response)):
                    break
                continue
            payload = response.json()
            operation = str(payload.get("name") or "")
            if operation:
                break
        if not operation:
            return _title_clip(db, tenant_id=tenant_id, actor_id=actor_id, headline=headline)
        poll_url = operation if operation.startswith("http") else f"{GEMINI_API_BASE}/{operation.removeprefix('/')}"
        deadline = time.monotonic() + 180
        done_payload: dict = {}
        failed = False
        while time.monotonic() < deadline:
            polled = client.get(poll_url, headers={"x-goog-api-key": key})
            if polled.status_code >= 400:
                failed = True
                break
            done_payload = polled.json()
            if done_payload.get("done"):
                break
            time.sleep(5)
        else:
            failed = True
        if failed or done_payload.get("error"):
            return _title_clip(db, tenant_id=tenant_id, actor_id=actor_id, headline=headline)
        uri = _video_uri(done_payload)
        if not uri:
            return _title_clip(db, tenant_id=tenant_id, actor_id=actor_id, headline=headline)
        downloaded = client.get(uri, headers={"x-goog-api-key": key}, timeout=60.0)
        if downloaded.status_code >= 400 or b"ftyp" not in downloaded.content[:32]:
            return _title_clip(db, tenant_id=tenant_id, actor_id=actor_id, headline=headline)
        return store_social_video(db, tenant_id=tenant_id, actor_id=actor_id, data=downloaded.content), ""


def _title_clip(db: Session, *, tenant_id: UUID, actor_id: UUID, headline: str) -> tuple[str, str]:
    clip = draw_title_clip(headline)
    return store_social_gif(db, tenant_id=tenant_id, actor_id=actor_id, data=clip), _CLIP_NOTE
