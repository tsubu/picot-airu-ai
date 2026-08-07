"""GraphRAG local entities/relations — loosely coupled to Hybrid RAG."""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Callable

ENTITY_TYPES = ("product", "problem", "cause", "action")
ProgressCallback = Callable[[str, float], None]

_PRODUCT_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{1,10}(?:-\d{1,5})+(?:[A-Z])?)(?![A-Za-z0-9])")
_PROBLEM_KEYWORDS = (
    "電源が入らない",
    "起動しない",
    "点滅",
    "返品",
    "配送",
    "エラー",
    "故障",
    "不具合",
)
_CAUSE_KEYWORDS = (
    "アダプター",
    "ケーブル",
    "バッテリー",
    "設定",
    "接続",
)
_ACTION_KEYWORDS = (
    "リセット",
    "再起動",
    "交換",
    "確認",
    "申請",
    "取扱説明書",
)


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def upsert_entity(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    name: str,
    description: str | None = None,
    source_qa_id: int | None = None,
) -> int:
    normalized = _norm(name)
    row = conn.execute(
        """
        SELECT id, source_qa_ids FROM graph_entities
        WHERE entity_type = ? AND normalized_name = ?
        """,
        (entity_type, normalized),
    ).fetchone()
    if row:
        qa_ids = set(filter(None, (row["source_qa_ids"] or "").split(",")))
        if source_qa_id is not None:
            qa_ids.add(str(source_qa_id))
        conn.execute(
            """
            UPDATE graph_entities
            SET description = COALESCE(?, description),
                source_qa_ids = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (description, ",".join(sorted(qa_ids)), row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO graph_entities(entity_type, name, normalized_name, description, source_qa_ids, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            entity_type,
            name.strip(),
            normalized,
            description,
            str(source_qa_id) if source_qa_id is not None else None,
        ),
    )
    return int(cur.lastrowid)


def add_relation(
    conn: sqlite3.Connection,
    *,
    from_id: int,
    to_id: int,
    relation_type: str,
    source_qa_id: int | None = None,
    weight: float = 1.0,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO graph_relations(
          from_entity_id, to_entity_id, relation_type, weight, source_qa_id, created_at
        ) VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (from_id, to_id, relation_type, weight, source_qa_id),
    )


def extract_entities_from_qa(question: str, answer: str) -> dict[str, list[str]]:
    text = f"{question}\n{answer}"
    products = list(dict.fromkeys(_PRODUCT_RE.findall(text)))
    problems = [k for k in _PROBLEM_KEYWORDS if k in text]
    causes = [k for k in _CAUSE_KEYWORDS if k in text]
    actions = [k for k in _ACTION_KEYWORDS if k in text]
    return {
        "product": products,
        "problem": problems,
        "cause": causes,
        "action": actions,
    }


def rebuild_graph(
    conn: sqlite3.Connection,
    *,
    clear_existing: bool = True,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    def report(stage: str, pct: float) -> None:
        if progress:
            progress(stage, pct)

    cur = conn.execute(
        """
        INSERT INTO graph_builds(started_at, status)
        VALUES (datetime('now'), 'running')
        """
    )
    build_id = int(cur.lastrowid)
    conn.commit()

    if clear_existing:
        conn.execute("DELETE FROM graph_relations")
        conn.execute("DELETE FROM graph_entities")
        conn.commit()

    rows = conn.execute("SELECT id, question, answer FROM qa_pairs ORDER BY id ASC").fetchall()
    total = len(rows)
    report("extract", 0.05)

    for idx, row in enumerate(rows, start=1):
        extracted = extract_entities_from_qa(row["question"] or "", row["answer"] or "")
        ids: dict[str, list[int]] = {t: [] for t in ENTITY_TYPES}
        for etype in ENTITY_TYPES:
            for name in extracted.get(etype, []):
                eid = upsert_entity(
                    conn,
                    entity_type=etype,
                    name=name,
                    source_qa_id=int(row["id"]),
                )
                ids[etype].append(eid)
        # product -> problem -> cause -> action chain
        for pid in ids["product"]:
            for prid in ids["problem"]:
                add_relation(conn, from_id=pid, to_id=prid, relation_type="has_problem", source_qa_id=int(row["id"]))
        for prid in ids["problem"]:
            for cid in ids["cause"]:
                add_relation(conn, from_id=prid, to_id=cid, relation_type="caused_by", source_qa_id=int(row["id"]))
            for aid in ids["action"]:
                add_relation(conn, from_id=prid, to_id=aid, relation_type="resolved_by", source_qa_id=int(row["id"]))
        for cid in ids["cause"]:
            for aid in ids["action"]:
                add_relation(conn, from_id=cid, to_id=aid, relation_type="mitigated_by", source_qa_id=int(row["id"]))

        if idx % 20 == 0 or idx == total:
            report("extract", 0.05 + 0.9 * (idx / max(total, 1)))

    entity_count = conn.execute("SELECT COUNT(*) AS c FROM graph_entities").fetchone()["c"]
    relation_count = conn.execute("SELECT COUNT(*) AS c FROM graph_relations").fetchone()["c"]
    conn.execute(
        """
        UPDATE graph_builds
        SET completed_at = datetime('now'),
            entity_count = ?,
            relation_count = ?,
            qa_processed = ?,
            status = 'completed'
        WHERE id = ?
        """,
        (entity_count, relation_count, total, build_id),
    )
    conn.commit()
    report("done", 1.0)
    return {
        "build_id": build_id,
        "entity_count": entity_count,
        "relation_count": relation_count,
        "qa_processed": total,
        "status": "completed",
    }


def local_search(conn: sqlite3.Connection, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Neighborhood search around entities matching the query tokens."""
    tokens = [t for t in re.findall(r"[A-Za-z0-9\-]+|[\u3040-\u30ff\u4e00-\u9fff]{2,}", query) if t]
    if not tokens:
        return []

    matched: list[sqlite3.Row] = []
    for token in tokens:
        rows = conn.execute(
            """
            SELECT * FROM graph_entities
            WHERE normalized_name LIKE ? OR name LIKE ? OR COALESCE(description, '') LIKE ?
            LIMIT 20
            """,
            (f"%{_norm(token)}%", f"%{token}%", f"%{token}%"),
        ).fetchall()
        matched.extend(rows)

    # dedupe entities
    entities = {int(r["id"]): dict(r) for r in matched}
    if not entities:
        return []

    results: list[dict[str, Any]] = []
    for eid, ent in entities.items():
        neighbors = conn.execute(
            """
            SELECT r.relation_type, r.weight, r.source_qa_id,
                   e.id AS entity_id, e.entity_type, e.name
            FROM graph_relations r
            JOIN graph_entities e ON e.id = CASE
              WHEN r.from_entity_id = ? THEN r.to_entity_id
              ELSE r.from_entity_id
            END
            WHERE r.from_entity_id = ? OR r.to_entity_id = ?
            LIMIT 20
            """,
            (eid, eid, eid),
        ).fetchall()
        score = 0.4 + 0.1 * len(neighbors)
        # product/model exact-ish boost
        if any(token.upper() in (ent["name"] or "").upper() for token in tokens if re.search(r"[A-Za-z]", token)):
            score += 0.3
        results.append(
            {
                "entity_id": eid,
                "entity_type": ent["entity_type"],
                "name": ent["name"],
                "score": min(1.0, score),
                "source": "graph",
                "neighbors": [dict(n) for n in neighbors],
                "qa_ids": [
                    int(x)
                    for x in (ent.get("source_qa_ids") or "").split(",")
                    if x.isdigit()
                ],
            }
        )

    results.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return results[:limit]


def graph_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    by_type = {
        row["entity_type"]: row["c"]
        for row in conn.execute(
            "SELECT entity_type, COUNT(*) AS c FROM graph_entities GROUP BY entity_type"
        ).fetchall()
    }
    last = conn.execute(
        "SELECT * FROM graph_builds WHERE status='completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {
        "entity_count": conn.execute("SELECT COUNT(*) AS c FROM graph_entities").fetchone()["c"],
        "relation_count": conn.execute("SELECT COUNT(*) AS c FROM graph_relations").fetchone()["c"],
        "by_type": by_type,
        "last_build": dict(last) if last else None,
    }


def trend_analysis(conn: sqlite3.Connection, *, limit: int = 10) -> list[dict[str, Any]]:
    """Minimal inquiry trend: frequent problem/product entities."""
    rows = conn.execute(
        """
        SELECT entity_type, name, COUNT(*) AS mentions
        FROM (
          SELECT e.entity_type, e.name
          FROM graph_entities e
          JOIN graph_relations r ON r.from_entity_id = e.id OR r.to_entity_id = e.id
          WHERE e.entity_type IN ('product', 'problem')
        )
        GROUP BY entity_type, name
        ORDER BY mentions DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
