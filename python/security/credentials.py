"""Credential and non-secret settings helpers."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import keyring

SERVICE_NAME = "MailRAGDesktop"
API_KEY_ACCOUNT = "gemini_api_key"


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
    if key == "gemini_api_key":
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
