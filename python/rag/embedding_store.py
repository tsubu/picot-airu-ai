"""LanceDB embedding store helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def table_names(db) -> list[str]:
    """Compatible table listing across LanceDB versions."""
    if hasattr(db, "list_tables"):
        try:
            listed = db.list_tables()
            if isinstance(listed, list):
                return [str(x) for x in listed]
            tables = getattr(listed, "tables", None)
            if tables is not None:
                return [str(x) for x in tables]
        except Exception:
            pass
    return list(db.table_names())


def upsert_qa_embeddings(
    lancedb_dir: Path,
    rows: list[dict[str, Any]],
) -> int:
    """rows: qa_id, question, answer, vector"""
    if not rows:
        return 0
    import lancedb

    lancedb_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(lancedb_dir))
    payload = [
        {
            "qa_id": int(r["qa_id"]),
            "question": r["question"],
            "answer": r["answer"],
            "vector": r["vector"],
        }
        for r in rows
    ]
    names = table_names(db)
    if "qa_embeddings" not in names:
        db.create_table("qa_embeddings", payload)
        return len(payload)

    table = db.open_table("qa_embeddings")
    ids = ", ".join(str(int(r["qa_id"])) for r in payload)
    try:
        table.delete(f"qa_id IN ({ids})")
        table.add(payload)
        return len(payload)
    except Exception as delete_exc:
        # Fallback: rebuild table keeping other rows to avoid silent duplicates
        try:
            existing = table.to_list()
            id_set = {int(r["qa_id"]) for r in payload}
            kept = [row for row in existing if int(row.get("qa_id")) not in id_set]
            rebuilt = kept + payload
            db.drop_table("qa_embeddings")
            if rebuilt:
                db.create_table("qa_embeddings", rebuilt)
            else:
                db.create_table("qa_embeddings", payload)
            return len(payload)
        except Exception as rebuild_exc:
            raise RuntimeError(
                f"Failed to upsert embeddings (delete={delete_exc}; rebuild={rebuild_exc})"
            ) from rebuild_exc
