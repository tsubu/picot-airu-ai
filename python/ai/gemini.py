"""AI provider abstraction and Gemini client."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, *, model: str | None = None) -> str:
        raise NotImplementedError


def _normalize_model_id(name: str | None) -> str | None:
    if not name:
        return None
    # API returns "models/gemini-2.0-flash" — store bare id for settings
    return name.split("/", 1)[-1] if name.startswith("models/") else name


def list_gemini_models(api_key: str) -> list[dict[str, Any]]:
    """Fetch available Gemini models and return serializable catalog entries."""
    from google import genai

    client = genai.Client(api_key=api_key)
    generative: list[dict[str, Any]] = []
    embedding: list[dict[str, Any]] = []

    pager = client.models.list(config={"page_size": 100})
    for model in pager:
        model_id = _normalize_model_id(getattr(model, "name", None))
        if not model_id:
            continue
        actions = [str(a).lower() for a in (getattr(model, "supported_actions", None) or [])]
        entry = {
            "id": model_id,
            "name": getattr(model, "name", None),
            "display_name": getattr(model, "display_name", None) or model_id,
            "description": getattr(model, "description", None),
            "supported_actions": list(getattr(model, "supported_actions", None) or []),
            "input_token_limit": getattr(model, "input_token_limit", None),
            "output_token_limit": getattr(model, "output_token_limit", None),
        }
        # Prefer explicit generateContent; also keep gemini-* as generative fallback
        if any("generatecontent" in a.replace("_", "") for a in actions) or (
            not actions and model_id.startswith("gemini-")
        ):
            generative.append(entry)
        if any("embedcontent" in a.replace("_", "") for a in actions) or (
            "embedding" in model_id or model_id.startswith("text-embedding")
        ):
            embedding.append(entry)

    generative.sort(key=lambda m: m["id"])
    embedding.sort(key=lambda m: m["id"])
    return [
        *[{"kind": "generate", **m} for m in generative],
        *[{"kind": "embed", **m} for m in embedding],
    ]


def filter_models(catalog: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [m for m in catalog if m.get("kind") == kind]


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, default_model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        client = self._get_client()
        used_model = model or self.default_model
        response = client.models.generate_content(model=used_model, contents=prompt)
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini returned empty response")
        return text


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        raise NotImplementedError


class GeminiEmbedding(EmbeddingProvider):
    def __init__(self, api_key: str, default_model: str = "text-embedding-004") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        client = self._get_client()
        used_model = model or self.default_model
        vectors: list[list[float]] = []
        for text in texts:
            result = client.models.embed_content(model=used_model, contents=text)
            # google-genai response shapes vary slightly by version
            embedding = None
            if hasattr(result, "embeddings") and result.embeddings:
                embedding = list(result.embeddings[0].values)
            elif hasattr(result, "embedding") and result.embedding is not None:
                embedding = list(result.embedding.values)
            if embedding is None:
                raise RuntimeError("Gemini embedding response missing values")
            vectors.append(embedding)
        return vectors
