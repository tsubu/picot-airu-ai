"""Reset imported knowledge data (mails / QA / vectors / graph)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any, Callable

from security.credentials import get_setting, set_setting

ProgressCallback = Callable[[str, float], None]

# Tables that hold imported / derived knowledge. Settings & credentials are kept.
_KNOWLEDGE_TABLES = (
    "rag_sources",
    "ai_responses",
    "conversation_summaries",
    "conversation_messages",
    "conversations",
    "qa_embedding_status",
    "qa_pairs",
    "graph_relations",
    "graph_entities",
    "graph_builds",
    "messages",
    "raw_messages",
    "imports",
)


def _clear_lancedb(lancedb_dir: Path | None) -> dict[str, Any]:
    if lancedb_dir is None or not lancedb_dir.exists():
        return {"cleared": False, "reason": "missing"}
    try:
        import lancedb

        from rag.embedding_store import table_names

        db = lancedb.connect(str(lancedb_dir))
        names = table_names(db)
        dropped = []
        for name in names:
            try:
                db.drop_table(name)
                dropped.append(name)
            except Exception:
                pass
        # If drop failed or leftover files remain, wipe directory contents
        if not dropped:
            for child in lancedb_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            return {"cleared": True, "mode": "rmtree"}
        return {"cleared": True, "dropped": dropped}
    except Exception as exc:
        # Last resort: remove the whole lancedb directory and recreate
        try:
            shutil.rmtree(lancedb_dir, ignore_errors=True)
            lancedb_dir.mkdir(parents=True, exist_ok=True)
            return {"cleared": True, "mode": "rmtree", "warning": str(exc)}
        except Exception as exc2:
            return {"cleared": False, "error": str(exc2)}


def reset_imported_data(
    conn: sqlite3.Connection,
    *,
    lancedb_dir: Path | None = None,
    include_conversations: bool = True,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Wipe imported mails, QA, Graph, embeddings. Keep settings / API keys."""

    def report(stage: str, pct: float) -> None:
        if progress:
            progress(stage, pct)

    before = {
        "messages": conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"],
        "qa": conn.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"],
        "conversations": conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"],
        "graph_entities": conn.execute("SELECT COUNT(*) AS c FROM graph_entities").fetchone()["c"],
        "imports": conn.execute("SELECT COUNT(*) AS c FROM imports").fetchone()["c"],
    }

    report("sqlite", 0.1)
    tables = list(_KNOWLEDGE_TABLES)
    if not include_conversations:
        tables = [
            t
            for t in tables
            if t
            not in {
                "rag_sources",
                "ai_responses",
                "conversation_summaries",
                "conversation_messages",
                "conversations",
            }
        ]

    # Disable FK briefly for bulk deletes of interdependent tables
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table in tables:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    report("faq", 0.55)
    if get_setting(conn, "faq_snapshot") is not None:
        set_setting(conn, "faq_snapshot", [])

    report("lancedb", 0.7)
    lance = _clear_lancedb(lancedb_dir)

    report("done", 1.0)
    after = {
        "messages": conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"],
        "qa": conn.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"],
        "conversations": conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"],
        "graph_entities": conn.execute("SELECT COUNT(*) AS c FROM graph_entities").fetchone()["c"],
        "imports": conn.execute("SELECT COUNT(*) AS c FROM imports").fetchone()["c"],
    }
    return {
        "success": True,
        "before": before,
        "after": after,
        "lancedb": lance,
        "include_conversations": include_conversations,
    }
