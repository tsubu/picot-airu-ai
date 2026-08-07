"""Safe application logging — never log API keys or full customer mail bodies."""

from __future__ import annotations

import sqlite3
from typing import Any


_FORBIDDEN_KEYS = {"api_key", "gemini_api_key", "authorization", "password"}


def _sanitize(detail: Any) -> str | None:
    if detail is None:
        return None
    text = str(detail)
    lowered = text.lower()
    for key in _FORBIDDEN_KEYS:
        if key in lowered:
            return "[redacted]"
    # Avoid dumping long mail bodies into logs
    if len(text) > 500:
        return text[:500] + "…[truncated]"
    return text


def log_event(conn: sqlite3.Connection, level: str, event: str, detail: Any = None) -> None:
    conn.execute(
        """
        INSERT INTO app_logs(level, event, detail, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (level, event, _sanitize(detail)),
    )
    conn.commit()
