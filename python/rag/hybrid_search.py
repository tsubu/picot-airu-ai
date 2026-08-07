"""Hybrid RAG: keyword + optional vector, with simple rerank."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


def _tokens(text: str) -> set[str]:
    parts = re.findall(r"[A-Za-z0-9\-]+|[\u3040-\u30ff\u4e00-\u9fff]+", text.lower())
    return {p for p in parts if len(p) >= 2}


class HybridSearch:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        lancedb_dir: Path | None = None,
        vector_limit: int = 20,
        keyword_limit: int = 20,
        top_k: int = 5,
    ) -> None:
        self.conn = conn
        self.lancedb_dir = lancedb_dir
        self.vector_limit = vector_limit
        self.keyword_limit = keyword_limit
        self.top_k = top_k

    def keyword_search(self, query: str) -> list[dict[str, Any]]:
        tokens = list(_tokens(query))
        rows = self.conn.execute(
            "SELECT id, question, answer, product, category FROM qa_pairs ORDER BY id DESC LIMIT 500"
        ).fetchall()
        scored: list[dict[str, Any]] = []
        q_tokens = _tokens(query)
        for row in rows:
            text = f"{row['question']}\n{row['answer']}\n{row['product'] or ''}"
            t = _tokens(text)
            if not t:
                continue
            overlap = len(q_tokens & t)
            # Bonus for exact product/model-like tokens
            bonus = 0.0
            for tok in tokens:
                if re.search(r"[A-Za-z]+\-?\d+", tok) and tok in text.lower():
                    bonus += 0.35
            if overlap == 0 and bonus == 0:
                continue
            score = min(1.0, overlap / max(len(q_tokens), 1) + bonus)
            scored.append(
                {
                    "qa_id": row["id"],
                    "question": row["question"],
                    "answer": row["answer"],
                    "score": score,
                    "source": "keyword",
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: self.keyword_limit]

    def vector_search(self, query: str, query_vector: list[float] | None = None) -> list[dict[str, Any]]:
        """Best-effort LanceDB search. Returns [] if unavailable."""
        if not self.lancedb_dir or query_vector is None:
            return []
        try:
            import lancedb
        except Exception:
            return []
        try:
            db = lancedb.connect(str(self.lancedb_dir))
            names = db.table_names()
            if "qa_embeddings" not in names:
                return []
            table = db.open_table("qa_embeddings")
            hits = table.search(query_vector).limit(self.vector_limit).to_list()
            results = []
            for hit in hits:
                # Lance distance -> crude similarity
                dist = float(hit.get("_distance") or hit.get("distance") or 0.5)
                score = max(0.0, 1.0 - dist)
                results.append(
                    {
                        "qa_id": hit.get("qa_id"),
                        "question": hit.get("question"),
                        "answer": hit.get("answer"),
                        "score": score,
                        "source": "vector",
                    }
                )
            return results
        except Exception:
            return []

    def merge_rerank(
        self,
        vector_hits: list[dict[str, Any]],
        keyword_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[Any, dict[str, Any]] = {}
        for hit in vector_hits + keyword_hits:
            qa_id = hit.get("qa_id")
            if qa_id is None:
                continue
            if qa_id not in merged:
                merged[qa_id] = dict(hit)
            else:
                # Prefer higher score; slight boost if both channels hit
                prev = merged[qa_id]
                combined = max(float(prev.get("score") or 0), float(hit.get("score") or 0)) + 0.05
                prev["score"] = min(1.0, combined)
                prev["source"] = "hybrid"
        ranked = sorted(merged.values(), key=lambda x: float(x.get("score") or 0), reverse=True)
        return ranked[: self.top_k]

    def search(self, query: str, query_vector: list[float] | None = None) -> list[dict[str, Any]]:
        keyword_hits = self.keyword_search(query)
        vector_hits = self.vector_search(query, query_vector=query_vector)
        return self.merge_rerank(vector_hits, keyword_hits)
