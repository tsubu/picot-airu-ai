"""AI / Embedding provider factory (Gemini / OpenAI / Claude / Ollama)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ai.gemini import AIProvider, EmbeddingProvider, GeminiEmbedding, GeminiProvider
from security.credentials import get_api_key, get_setting

SERVICE_NAME = "MailRAGDesktop"


class OpenAIProvider(AIProvider):
    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        used = model or self.default_model
        payload = {
            "model": used,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


class ClaudeProvider(AIProvider):
    """Anthropic Claude Messages API."""

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "claude-sonnet-4-5",
        base_url: str = "https://api.anthropic.com",
        api_version: str = "2023-06-01",
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        used = model or self.default_model
        payload = {
            "model": used,
            "max_tokens": 2048,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Claude API error {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Claude API に接続できません: {exc}") from exc

        content = data.get("content") or []
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(t for t in texts if t).strip()
        if not text:
            raise RuntimeError("Claude returned empty response")
        return text


class OllamaProvider(AIProvider):
    def __init__(
        self,
        *,
        default_model: str = "llama3.2",
        base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        used = model or self.default_model
        payload = {"model": used, "prompt": prompt, "stream": False}
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama に接続できません ({self.base_url}): {exc}") from exc
        text = data.get("response")
        if not text:
            raise RuntimeError("Ollama returned empty response")
        return text


class OpenAIEmbedding(EmbeddingProvider):
    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        used = model or self.default_model
        payload = {"model": used, "input": texts}
        req = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = sorted(data["data"], key=lambda x: x["index"])
        return [list(item["embedding"]) for item in items]


def get_openai_api_key() -> str | None:
    import keyring

    return keyring.get_password(SERVICE_NAME, "openai_api_key")


def set_openai_api_key(api_key: str) -> None:
    import keyring

    keyring.set_password(SERVICE_NAME, "openai_api_key", api_key)


def get_claude_api_key() -> str | None:
    import keyring

    return keyring.get_password(SERVICE_NAME, "claude_api_key")


def set_claude_api_key(api_key: str) -> None:
    import keyring

    keyring.set_password(SERVICE_NAME, "claude_api_key", api_key)


def build_ai_provider(conn) -> AIProvider | None:
    provider = str(get_setting(conn, "ai_provider", "gemini") or "gemini").lower()
    if provider in {"claude", "anthropic"}:
        key = get_claude_api_key()
        if not key:
            return None
        return ClaudeProvider(
            key,
            default_model=str(get_setting(conn, "reply_model", "claude-sonnet-4-5")),
            base_url=str(get_setting(conn, "claude_base_url", "https://api.anthropic.com")),
        )
    if provider == "ollama":
        return OllamaProvider(
            default_model=str(get_setting(conn, "ollama_model", "llama3.2")),
            base_url=str(get_setting(conn, "ollama_base_url", "http://127.0.0.1:11434")),
        )
    if provider == "openai":
        key = get_openai_api_key()
        if not key:
            return None
        return OpenAIProvider(
            key,
            default_model=str(get_setting(conn, "reply_model", "gpt-4o-mini")),
            base_url=str(get_setting(conn, "openai_base_url", "https://api.openai.com/v1")),
        )
    key = get_api_key()
    if not key:
        return None
    return GeminiProvider(key, default_model=str(get_setting(conn, "reply_model", "gemini-2.5-flash")))


def build_embedding_provider(conn) -> EmbeddingProvider | None:
    provider = str(
        get_setting(conn, "embedding_provider", get_setting(conn, "ai_provider", "gemini")) or "gemini"
    ).lower()
    # Claude has no public embedding API here — use explicit embedding provider or Gemini
    if provider in {"claude", "anthropic"}:
        provider = str(get_setting(conn, "embedding_provider_fallback", "gemini") or "gemini").lower()
        if provider in {"claude", "anthropic"}:
            provider = "gemini"
    if provider == "openai":
        key = get_openai_api_key()
        if not key:
            return None
        return OpenAIEmbedding(
            key,
            default_model=str(get_setting(conn, "embedding_model", "text-embedding-3-small")),
            base_url=str(get_setting(conn, "openai_base_url", "https://api.openai.com/v1")),
        )
    if provider == "ollama":
        return None
    key = get_api_key()
    if not key:
        return None
    return GeminiEmbedding(
        key,
        default_model=str(get_setting(conn, "embedding_model", "text-embedding-004")),
    )


def provider_auth_status(conn) -> dict[str, Any]:
    """Return whether the selected AI provider can authenticate (key present / local)."""
    provider = str(get_setting(conn, "ai_provider", "gemini") or "gemini").lower()
    if provider in {"claude", "anthropic"}:
        ready = bool(get_claude_api_key())
        return {
            "provider": "claude",
            "ready": ready,
            "requires_api_key": True,
            "code": "ok" if ready else "missing_api_key",
            "message": (
                None
                if ready
                else "Claude（Anthropic）の APIキーが未設定です。設定画面で登録してください。"
            ),
        }
    if provider == "openai":
        ready = bool(get_openai_api_key())
        return {
            "provider": "openai",
            "ready": ready,
            "requires_api_key": True,
            "code": "ok" if ready else "missing_api_key",
            "message": (
                None
                if ready
                else "OpenAI の APIキーが未設定です。設定画面で登録してください。"
            ),
        }
    if provider == "ollama":
        return {
            "provider": "ollama",
            "ready": True,
            "requires_api_key": False,
            "code": "ok",
            "message": None,
        }
    ready = bool(get_api_key())
    return {
        "provider": "gemini",
        "ready": ready,
        "requires_api_key": True,
        "code": "ok" if ready else "missing_api_key",
        "message": (
            None
            if ready
            else "Gemini の APIキーが未設定です。設定画面で登録してください。"
        ),
    }


def classify_provider_error(exc: BaseException) -> dict[str, str]:
    """Map provider exceptions to stable error_code + user-facing Japanese message."""
    text = str(exc)
    low = text.lower()
    if any(
        x in low
        for x in (
            "401",
            "403",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "authentication",
            "permission_denied",
            "api key not valid",
            "invalid_api_key",
            "invalid x-api-key",
        )
    ):
        return {
            "error_code": "invalid_api_key",
            "error": "APIキーが正しくないか、権限がありません。設定画面でキーを確認・再登録してください。",
        }
    if any(x in low for x in ("429", "quota", "resource_exhausted", "rate limit", "insufficient_quota")):
        return {
            "error_code": "api_quota",
            "error": "APIの利用上限に達している可能性があります。しばらく待つか、プラン／課金を確認してください。",
        }
    if any(
        x in low
        for x in (
            "timed out",
            "timeout",
            "connection refused",
            "failed to establish",
            "name or service not known",
            "nodename nor servname",
            "unreachable",
            "temporary failure",
            "network is unreachable",
        )
    ):
        return {
            "error_code": "api_unreachable",
            "error": "AIサービスに接続できません。ネットワーク接続とプロバイダの稼働状況を確認してください。",
        }
    return {
        "error_code": "api_error",
        "error": f"AIサービスでエラーが発生しました: {text[:240]}",
    }


def list_provider_models(conn) -> dict[str, Any]:
    provider = str(get_setting(conn, "ai_provider", "gemini") or "gemini").lower()
    if provider == "ollama":
        base = str(get_setting(conn, "ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
        try:
            with urllib.request.urlopen(f"{base}/api/tags", timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [
                {"id": m.get("name"), "display_name": m.get("name"), "kind": "generate"}
                for m in data.get("models", [])
                if m.get("name")
            ]
            return {"success": True, "provider": "ollama", "reply_models": models}
        except Exception as exc:
            return {"success": False, "error": f"Ollamaモデル取得失敗: {exc}"}
    if provider == "openai":
        models = [
            {"id": "gpt-4o-mini", "display_name": "gpt-4o-mini", "kind": "generate"},
            {"id": "gpt-4o", "display_name": "gpt-4o", "kind": "generate"},
            {"id": "gpt-4.1-mini", "display_name": "gpt-4.1-mini", "kind": "generate"},
        ]
        return {"success": True, "provider": "openai", "reply_models": models}
    if provider in {"claude", "anthropic"}:
        models = [
            {"id": "claude-sonnet-4-5", "display_name": "Claude Sonnet 4.5", "kind": "generate"},
            {"id": "claude-opus-4-5", "display_name": "Claude Opus 4.5", "kind": "generate"},
            {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5", "kind": "generate"},
            {"id": "claude-3-5-sonnet-latest", "display_name": "Claude 3.5 Sonnet (latest)", "kind": "generate"},
            {"id": "claude-3-5-haiku-latest", "display_name": "Claude 3.5 Haiku (latest)", "kind": "generate"},
        ]
        return {"success": True, "provider": "claude", "reply_models": models}
    return {"success": False, "error": "gemini は refresh_models を使ってください"}
