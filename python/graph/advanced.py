"""Graph Global / DRIFT search, FAQ generation, knowledge analysis."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any

from graph import local_search, trend_analysis


def global_search(conn: sqlite3.Connection, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """
    Global-ish search: rank entity communities by query overlap and relation density.
    Not Microsoft GraphRAG Global; a local OSS approximation using entity hubs.
    """
    local = local_search(conn, query, limit=20)
    if not local:
        # fallback: top hubs by degree
        rows = conn.execute(
            """
            SELECT e.id, e.entity_type, e.name, COUNT(r.id) AS degree
            FROM graph_entities e
            LEFT JOIN graph_relations r
              ON r.from_entity_id = e.id OR r.to_entity_id = e.id
            GROUP BY e.id
            ORDER BY degree DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "mode": "global",
                "entity_id": row["id"],
                "entity_type": row["entity_type"],
                "name": row["name"],
                "score": min(1.0, 0.2 + 0.05 * int(row["degree"] or 0)),
                "degree": row["degree"],
                "summary": f"高接続ハブ: {row['entity_type']}:{row['name']}",
            }
            for row in rows
        ]

    # Expand each local hit into a community summary
    communities: list[dict[str, Any]] = []
    for hit in local:
        eid = int(hit["entity_id"])
        neigh = hit.get("neighbors") or []
        types = defaultdict(list)
        types[hit["entity_type"]].append(hit["name"])
        for n in neigh:
            types[n.get("entity_type") or "unknown"].append(n.get("name") or "")
        summary_parts = []
        for t in ("product", "problem", "cause", "action"):
            names = [x for x in dict.fromkeys(types.get(t, [])) if x]
            if names:
                summary_parts.append(f"{t}={', '.join(names[:3])}")
        communities.append(
            {
                "mode": "global",
                "entity_id": eid,
                "entity_type": hit["entity_type"],
                "name": hit["name"],
                "score": min(1.0, float(hit.get("score") or 0) + 0.1 * min(len(neigh), 5)),
                "degree": len(neigh),
                "summary": "; ".join(summary_parts) or hit["name"],
                "qa_ids": hit.get("qa_ids") or [],
            }
        )
    communities.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return communities[:limit]


def drift_search(conn: sqlite3.Connection, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """
    DRIFT-like blend: start local, then drift into global community context.
    """
    local = local_search(conn, query, limit=limit)
    glob = global_search(conn, query, limit=limit)
    merged: dict[str, dict[str, Any]] = {}
    for item in local:
        key = f"local:{item.get('entity_id')}"
        merged[key] = {**item, "mode": "drift-local", "score": float(item.get("score") or 0)}
    for item in glob:
        key = f"global:{item.get('entity_id')}"
        if key in merged:
            merged[key]["score"] = min(1.0, float(merged[key]["score"]) + 0.15)
            merged[key]["mode"] = "drift-both"
            merged[key]["summary"] = item.get("summary") or merged[key].get("summary")
        else:
            merged[key] = {
                **item,
                "mode": "drift-global",
                "score": float(item.get("score") or 0) * 0.9,
            }
    ranked = sorted(merged.values(), key=lambda x: float(x.get("score") or 0), reverse=True)
    return ranked[:limit]


def knowledge_analysis(conn: sqlite3.Connection) -> dict[str, Any]:
    qa_total = conn.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    verified = conn.execute(
        "SELECT COUNT(*) AS c FROM qa_pairs WHERE verified = 1"
    ).fetchone()["c"]
    products = conn.execute(
        "SELECT COUNT(*) AS c FROM graph_entities WHERE entity_type='product'"
    ).fetchone()["c"]
    problems = conn.execute(
        "SELECT COUNT(*) AS c FROM graph_entities WHERE entity_type='problem'"
    ).fetchone()["c"]
    uncovered = conn.execute(
        """
        SELECT COUNT(*) AS c FROM qa_pairs q
        WHERE NOT EXISTS (
          SELECT 1 FROM graph_entities e
          WHERE ',' || COALESCE(e.source_qa_ids,'') || ',' LIKE '%,' || q.id || ',%'
        )
        """
    ).fetchone()["c"]
    top_relations = conn.execute(
        """
        SELECT relation_type, COUNT(*) AS c
        FROM graph_relations
        GROUP BY relation_type
        ORDER BY c DESC
        """
    ).fetchall()
    return {
        "qa_total": qa_total,
        "qa_verified": verified,
        "products": products,
        "problems": problems,
        "qa_without_graph_link": uncovered,
        "relation_breakdown": [dict(r) for r in top_relations],
        "trends": trend_analysis(conn, limit=15),
        "coverage_ratio": round((qa_total - uncovered) / qa_total, 3) if qa_total else 0.0,
    }


def generate_faqs(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict[str, Any]]:
    """
    Auto FAQ from high-degree problem entities + linked QA answers.
    """
    problems = conn.execute(
        """
        SELECT e.id, e.name, e.source_qa_ids, COUNT(r.id) AS degree
        FROM graph_entities e
        LEFT JOIN graph_relations r ON r.from_entity_id = e.id OR r.to_entity_id = e.id
        WHERE e.entity_type = 'problem'
        GROUP BY e.id
        ORDER BY degree DESC, e.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    faqs: list[dict[str, Any]] = []
    for row in problems:
        qa_ids = [int(x) for x in (row["source_qa_ids"] or "").split(",") if x.isdigit()]
        answer = None
        question = f"{row['name']}について教えてください"
        source_qa_id = None
        if qa_ids:
            qa = conn.execute(
                "SELECT id, question, answer FROM qa_pairs WHERE id = ?",
                (qa_ids[0],),
            ).fetchone()
            if qa:
                question = qa["question"]
                answer = qa["answer"]
                source_qa_id = qa["id"]
        if not answer:
            # synthesize short answer from neighbor actions
            actions = conn.execute(
                """
                SELECT e.name FROM graph_relations r
                JOIN graph_entities e ON e.id = r.to_entity_id
                WHERE r.from_entity_id = ? AND e.entity_type = 'action'
                LIMIT 3
                """,
                (row["id"],),
            ).fetchall()
            if actions:
                answer = " / ".join(a["name"] for a in actions) + " を確認してください。"
            else:
                answer = "関連する過去対応を確認のうえ、個別にご案内します。"
        faqs.append(
            {
                "question": question,
                "answer": answer,
                "problem": row["name"],
                "degree": row["degree"],
                "source_qa_id": source_qa_id,
            }
        )

    # Persist snapshot for export/UI
    conn.execute(
        """
        INSERT INTO settings(key, value, updated_at)
        VALUES ('faq_snapshot', ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')
        """,
        (json.dumps(faqs, ensure_ascii=False),),
    )
    conn.commit()
    return faqs
