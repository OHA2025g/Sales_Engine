import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.provider_resolve import resolve_channel


@dataclass
class CompletionResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    is_mock: bool
    estimated_cost: float


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
        _ = reasoning
        started = time.perf_counter()
        snippet = prompt[:400].replace("\n", " ")
        text = (
            "[MOCK LLM] Grounded response using retrieved tools and knowledge only. "
            f"System={system[:80]}. Prompt excerpt: {snippet}"
        )
        if "email" in system.lower() or "draft" in prompt.lower():
            text = (
                "Subject: Follow-up from AGRAYIAN AI Labs\n\n"
                "Hello,\n\nBased on the account context provided by tools, I recommend a concise "
                "follow-up that restates the stated problem and proposes a 30-minute discovery. "
                "This draft is not sent.\n\nRegards,\nAGRAYIAN Revenue OS"
            )
        latency = int((time.perf_counter() - started) * 1000)
        return CompletionResult(
            text=text,
            provider="mock",
            model=model or "mock-llm",
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            latency_ms=latency,
            is_mock=True,
            estimated_cost=0.0,
        )


class MockEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * 32
            for i, ch in enumerate(text.lower()):
                vec[i % 32] += (ord(ch) % 13) / 13.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class NotConfiguredLLMProvider(LLMProvider):
    def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
        _ = (prompt, system, reasoning)
        text = "[NOT_CONFIGURED LLM] GEMINI_API_KEY is missing. No model was called."
        return CompletionResult(
            text=text,
            provider="gemini",
            model=model or "not-configured",
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            is_mock=False,
            estimated_cost=0.0,
        )


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def gemini_model_id(model: str) -> str:
    return model.strip().removeprefix("models/")


def _gemini_error_message(response: object) -> str:
    reader = getattr(response, "json", None)
    payload = reader() if callable(reader) else {}
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if not isinstance(error, dict):
        return ""
    return str(error.get("message") or "").strip()


def gemini_reply_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("thought"):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return "".join(texts)


class GeminiLLMProvider(LLMProvider):
    def __init__(self, api_key: str = "", client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

    def complete(self, prompt: str, *, system: str, model: str | None = None, reasoning: bool = False) -> CompletionResult:
        settings = get_settings()
        if model:
            chosen = model
        elif reasoning and settings.gemini_reasoning_model:
            chosen = settings.gemini_reasoning_model
        else:
            chosen = settings.gemini_default_model or settings.gemini_fast_model
        if not chosen:
            raise RuntimeError("GEMINI_DEFAULT_MODEL is not configured")
        api_key = self._api_key or settings.gemini_api_key
        model_id = gemini_model_id(chosen)
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        if reasoning:
            body["generationConfig"] = {"thinkingConfig": {"thinkingBudget": 2048}}
        client = self._client or httpx.Client(timeout=60.0)
        close = self._client is None
        started = time.perf_counter()
        try:
            response = client.post(
                f"{GEMINI_API_BASE}/models/{model_id}:generateContent",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=body,
            )
            status = getattr(response, "status_code", 200)
            if status == 429:
                detail = _gemini_error_message(response)
                raise RuntimeError(detail or "Gemini quota is used up.")
            response.raise_for_status()
            payload = response.json()
        finally:
            if close:
                client.close()
        usage = payload.get("usageMetadata") or {}
        return CompletionResult(
            text=gemini_reply_text(payload),
            provider="gemini",
            model=str(payload.get("modelVersion") or model_id),
            input_tokens=int(usage.get("promptTokenCount") or 0),
            output_tokens=int(usage.get("candidatesTokenCount") or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
            is_mock=False,
            estimated_cost=0.0,
        )


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str = "", client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        settings = get_settings()
        model = settings.gemini_embedding_model
        if not model:
            raise RuntimeError("GEMINI_EMBEDDING_MODEL is not configured")
        api_key = self._api_key or settings.gemini_api_key
        model_id = gemini_model_id(model)
        client = self._client or httpx.Client(timeout=60.0)
        close = self._client is None
        try:
            response = client.post(
                f"{GEMINI_API_BASE}/models/{model_id}:batchEmbedContents",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "requests": [
                        {
                            "model": f"models/{model_id}",
                            "content": {"parts": [{"text": text}]},
                            "taskType": "SEMANTIC_SIMILARITY",
                        }
                        for text in texts
                    ]
                },
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if close:
                client.close()
        return [list((item or {}).get("values") or []) for item in payload.get("embeddings") or []]


def get_llm_provider(db: Session | None = None, tenant_id: UUID | None = None) -> LLMProvider:
    settings = get_settings()
    if db is not None and tenant_id is not None:
        resolved = resolve_channel(db, tenant_id, "gemini")
        if resolved.mode == "LIVE" and resolved.secrets.get("access_token"):
            return GeminiLLMProvider(api_key=resolved.secrets["access_token"])
        if resolved.mode == "NOT_CONFIGURED" or settings.llm_provider == "gemini":
            return NotConfiguredLLMProvider()
        return MockLLMProvider()
    if settings.llm_provider == "gemini":
        if settings.gemini_api_key:
            return GeminiLLMProvider()
        return NotConfiguredLLMProvider()
    return MockLLMProvider()


def get_embedding_provider(db: Session | None = None, tenant_id: UUID | None = None) -> EmbeddingProvider:
    settings = get_settings()
    if not settings.gemini_embedding_model:
        return MockEmbeddingProvider()
    if db is not None and tenant_id is not None:
        resolved = resolve_channel(db, tenant_id, "gemini")
        if resolved.mode == "LIVE" and resolved.secrets.get("access_token"):
            return GeminiEmbeddingProvider(api_key=resolved.secrets["access_token"])
    if settings.resolved_llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiEmbeddingProvider()
    return MockEmbeddingProvider()
