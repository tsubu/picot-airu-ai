"""Conversation summary helpers."""

from __future__ import annotations

import sqlite3


def get_summary(conn: sqlite3.Connection, conversation_id: int) -> str | None:
    row = conn.execute(
        "SELECT summary FROM conversation_summaries WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    if row:
        return row["summary"]
    row2 = conn.execute("SELECT summary FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return row2["summary"] if row2 else None


def upsert_summary(conn: sqlite3.Connection, conversation_id: int, summary: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_summaries(conversation_id, summary, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(conversation_id) DO UPDATE SET
          summary=excluded.summary,
          updated_at=datetime('now')
        """,
        (conversation_id, summary),
    )
    conn.execute(
        "UPDATE conversations SET summary = ?, updated_at = datetime('now') WHERE id = ?",
        (summary, conversation_id),
    )
    conn.commit()


def build_extractive_summary(messages: list[dict[str, str]], limit: int = 8) -> str:
    """Fallback summary without Gemini — keeps key recent lines."""
    lines: list[str] = []
    for msg in messages[-limit:]:
        role = "お客様" if msg["role"] == "customer" else "AI"
        snippet = msg["content"].replace("\n", " ").strip()
        if len(snippet) > 120:
            snippet = snippet[:120] + "…"
        lines.append(f"{role}: {snippet}")
    return "\n".join(lines)
