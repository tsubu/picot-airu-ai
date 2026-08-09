"""Incremental embedding after new QA inserts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ai.gemini import EmbeddingProvider
from ai.providers import build_embedding_provider
from rag.embedding_store import upsert_qa_embeddings
from security.credentials import get_setting


def pending_qa_ids(conn: sqlite3.Connection, limit: int = 200) -> list[int]:
    rows = conn.execute(
        """
        SELECT q.id
        FROM qa_pairs q
        LEFT JOIN qa_embedding_status s ON s.qa_id = q.id
        WHERE s.qa_id IS NULL
        ORDER BY q.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [int(r["id"]) for r in rows]


def mark_embedded(conn: sqlite3.Connection, qa_ids: list[int]) -> None:
    for qa_id in qa_ids:
        conn.execute(
            """
            INSERT INTO qa_embedding_status(qa_id, embedded_at)
            VALUES (?, datetime('now'))
            ON CONFLICT(qa_id) DO UPDATE SET embedded_at = datetime('now')
            """,
            (qa_id,),
        )
    conn.commit()


def embed_new_qa_pairs(
    conn: sqlite3.Connection,
    *,
    lancedb_dir: Path,
    qa_ids: list[int] | None = None,
    embedder: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    """Embed only new QA rows. Never embeds AI reply drafts into knowledge."""
    ids = qa_ids if qa_ids is not None else pending_qa_ids(conn)
    if not ids:
        return {"embedded": 0}

    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, question, answer FROM qa_pairs WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    if not rows:
        return {"embedded": 0}

    if embedder is None:
        embedder = build_embedding_provider(conn)
        if embedder is None:
            return {"embedded": 0, "skipped": "no_api_key"}

    texts = [f"Q: {r['question']}\nA: {r['answer']}" for r in rows]
    model = get_setting(conn, "embedding_model")
    try:
        vectors = embedder.embed(texts, model=str(model) if model else None)
    except Exception as exc:
        return {"embedded": 0, "error": str(exc)}
    if not vectors or len(vectors) != len(rows):
        return {"embedded": 0, "error": "embedding provider returned incomplete vectors"}
    payload = [
        {
            "qa_id": int(r["id"]),
            "question": r["question"],
            "answer": r["answer"],
            "vector": vectors[i],
        }
        for i, r in enumerate(rows)
    ]
    try:
        count = upsert_qa_embeddings(lancedb_dir, payload)
    except Exception as exc:
        return {"embedded": 0, "error": str(exc)}
    mark_embedded(conn, [int(r["id"]) for r in rows])
    return {"embedded": count}
