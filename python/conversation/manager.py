"""Conversation management."""

from __future__ import annotations

import sqlite3
from typing import Any

from mail.cleaner import clean_body


def create_conversation(conn: sqlite3.Connection, title: str, first_message: str) -> dict[str, Any]:
    cur = conn.execute(
        """
        INSERT INTO conversations(title, status, created_at, updated_at)
        VALUES (?, 'active', datetime('now'), datetime('now'))
        """,
        (title,),
    )
    conversation_id = int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO conversation_messages(conversation_id, role, content, created_at)
        VALUES (?, 'customer', ?, datetime('now'))
        """,
        (conversation_id, first_message),
    )
    conn.commit()
    return get_conversation(conn, conversation_id)


def append_customer_message(conn: sqlite3.Connection, conversation_id: int, content: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_messages(conversation_id, role, content, created_at)
        VALUES (?, 'customer', ?, datetime('now'))
        """,
        (conversation_id, content),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )
    conn.commit()


def append_ai_message(
    conn: sqlite3.Connection,
    conversation_id: int,
    content: str,
    *,
    model: str | None,
    confidence: float | None,
    sources: list[dict[str, Any]],
    status: str = "ok",
    error_message: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO conversation_messages(conversation_id, role, content, created_at)
        VALUES (?, 'ai', ?, datetime('now'))
        """,
        (conversation_id, content),
    )
    message_id = int(cur.lastrowid)
    cur2 = conn.execute(
        """
        INSERT INTO ai_responses(conversation_id, message_id, model, prompt_version, confidence, status, error_message, created_at)
        VALUES (?, ?, ?, 'v1', ?, ?, ?, datetime('now'))
        """,
        (conversation_id, message_id, model, confidence, status, error_message),
    )
    ai_response_id = int(cur2.lastrowid)
    for rank, source in enumerate(sources, start=1):
        conn.execute(
            """
            INSERT INTO rag_sources(ai_response_id, qa_id, score, rank)
            VALUES (?, ?, ?, ?)
            """,
            (ai_response_id, source.get("qa_id"), source.get("score"), rank),
        )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )
    conn.commit()
    return ai_response_id


def list_conversations(conn: sqlite3.Connection, query: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if query and query.strip():
        where = """
        WHERE c.title LIKE ?
           OR COALESCE(c.summary, '') LIKE ?
           OR EXISTS (
             SELECT 1 FROM conversation_messages cm
             WHERE cm.conversation_id = c.id AND cm.content LIKE ?
           )
        """
        like = f"%{query.strip()}%"
        params = [like, like, like]
    rows = conn.execute(
        f"""
        SELECT c.*,
               (
                 SELECT COUNT(*) FROM conversation_messages cm
                 WHERE cm.conversation_id = c.id AND cm.role = 'customer'
               ) AS turn_count
        FROM conversations c
        {where}
        ORDER BY c.updated_at DESC
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["status_label"] = "継続中" if item["status"] == "active" else "完了"
        result.append(item)
    return result


def get_conversation(conn: sqlite3.Connection, conversation_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if row is None:
        raise ValueError(f"conversation not found: {conversation_id}")
    messages = conn.execute(
        """
        SELECT * FROM conversation_messages
        WHERE conversation_id = ?
        ORDER BY id ASC
        """,
        (conversation_id,),
    ).fetchall()
    data = dict(row)
    data["messages"] = [dict(m) for m in messages]
    data["status_label"] = "継続中" if data["status"] == "active" else "完了"
    return data


def update_title(conn: sqlite3.Connection, conversation_id: int, title: str) -> None:
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (title, conversation_id),
    )
    conn.commit()


def set_status(conn: sqlite3.Connection, conversation_id: int, status: str) -> None:
    if status not in {"active", "completed"}:
        raise ValueError("status must be active or completed")
    conn.execute(
        "UPDATE conversations SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, conversation_id),
    )
    conn.commit()


def recent_context(conn: sqlite3.Connection, conversation_id: int, max_turns: int = 4) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT role, content FROM conversation_messages
        WHERE conversation_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (conversation_id, max_turns * 2),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(list(rows))]


def make_title_from_text(text: str, max_len: int = 40) -> str:
    cleaned = clean_body(text).replace("\n", " ").strip()
    if not cleaned:
        return "新しい問い合わせ"
    return cleaned[:max_len] + ("…" if len(cleaned) > max_len else "")
