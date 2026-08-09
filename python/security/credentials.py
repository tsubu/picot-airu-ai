"""Credential and non-secret settings helpers."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

import keyring

SERVICE_NAME = "MailRAGDesktop"
API_KEY_ACCOUNT = "gemini_api_key"
SECRET_SETTING_KEYS = frozenset(
    {
        "gemini_api_key",
        "api_key",
        "openai_api_key",
        "claude_api_key",
    }
)


def set_api_key(api_key: str) -> None:
    keyring.set_password(SERVICE_NAME, API_KEY_ACCOUNT, api_key)


def get_api_key() -> str | None:
    return keyring.get_password(SERVICE_NAME, API_KEY_ACCOUNT)


def delete_api_key() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, API_KEY_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    if key in SECRET_SETTING_KEYS:
        raise ValueError("API key must not be stored in SQLite")
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO settings(key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')
        """,
        (key, payload),
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    raw = row["value"]
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


def as_bool(value: Any, default: bool = False) -> bool:
    """Coerce settings values safely (JSON strings like \"false\" must be False)."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
        return default
    return bool(value)


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_str_list(value: Any) -> list[str]:
    """Normalize staff address/domain settings into a clean string list."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;\n]", value) if "," in value or ";" in value or "\n" in value else [value]
        return [p.strip() for p in parts if p and p.strip()]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    return []


def setting_exists(conn: sqlite3.Connection, key: str) -> bool:
    row = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone()
    return row is not None


def ensure_default_settings(conn: sqlite3.Connection) -> None:
    """Seed non-secret defaults once so UI placeholders match DB behavior."""
    defaults: dict[str, Any] = {
        "staff_addresses": [],
        "staff_domains": [],
        "allow_offline_draft": False,
        "mask_email": True,
        "mask_phone": True,
        "mask_address": True,
        "mask_name": False,
        "mask_order_id": False,
        "use_graph_rag": True,
        "rag_top_k": 5,
        "rag_min_score": 0.25,
        "ui_theme": "system",
    }
    for key, value in defaults.items():
        if not setting_exists(conn, key):
            set_setting(conn, key, value)
