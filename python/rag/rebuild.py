"""RAG rebuild helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

from rag.incremental import embed_new_qa_pairs, pending_qa_ids

ProgressCallback = Callable[[str, float], None]


def rebuild_embeddings(
    conn: sqlite3.Connection,
    *,
    lancedb_dir: Path,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Clear embedding status and re-embed all QA pairs."""
    def report(stage: str, pct: float) -> None:
        if progress:
            progress(stage, pct)

    report("clear", 0.05)
    conn.execute("DELETE FROM qa_embedding_status")
    conn.commit()

    # Optionally drop lance table
    try:
        import lancedb

        db = lancedb.connect(str(lancedb_dir))
        from rag.embedding_store import table_names

        if "qa_embeddings" in table_names(db):
            db.drop_table("qa_embeddings")
    except Exception:
        pass

    report("embed", 0.2)
    # Process in batches via pending ids
    total = conn.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    embedded = 0
    while True:
        ids = pending_qa_ids(conn, limit=50)
        if not ids:
            break
        result = embed_new_qa_pairs(conn, lancedb_dir=lancedb_dir, qa_ids=ids)
        if result.get("skipped") == "no_api_key":
            # Leave ids unmarked so a later rebuild can retry
            return {
                "success": False,
                "error": "APIキーが未設定のため Embedding 再構築を完了できません",
                "embedded": embedded,
                "total": total,
            }
        batch = int(result.get("embedded") or 0)
        if batch == 0:
            # Do not mark as embedded when vectors were not written
            return {
                "success": False,
                "error": result.get("error")
                or "Embedding に失敗したため再構築を中断しました（未埋め込みのまま残しています）",
                "embedded": embedded,
                "total": total,
                "pending": ids,
            }
        embedded += batch
        report("embed", 0.2 + 0.75 * (embedded / max(total, 1)))

    report("done", 1.0)
    return {"success": True, "embedded": embedded, "total": total}
