"""LanceDB embedding store helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
    names = db.table_names()
    if "qa_embeddings" in names:
        table = db.open_table("qa_embeddings")
        # delete existing ids then add
        ids = ", ".join(str(int(r["qa_id"])) for r in payload)
        try:
            table.delete(f"qa_id IN ({ids})")
        except Exception:
            pass
        table.add(payload)
    else:
        db.create_table("qa_embeddings", payload)
    return len(payload)
