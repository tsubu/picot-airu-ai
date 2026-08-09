"""Import pipeline: parse → dedupe → persist RAW/normalized → optional QA."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

from ai.qa_extractor import extract_qa_with_rules
from importer import import_messages
from mail.cleaner import clean_body
from mail.dedupe import body_hash, serialize_raw
from mail.role_detector import RoleDetector, RoleDetectorConfig


ProgressCallback = Callable[[str, float], None]


def run_import(
    conn: sqlite3.Connection,
    *,
    source_type: str,
    path: Path,
    staff_addresses: list[str] | None = None,
    staff_domains: list[str] | None = None,
    progress: ProgressCallback | None = None,
    lancedb_dir: Path | None = None,
) -> dict[str, Any]:
    def report(stage: str, pct: float) -> None:
        if progress:
            progress(stage, pct)

    report("parse", 0.05)
    messages = import_messages(source_type, path)
    # QA pairing is sequential (customer then staff); process chronological order
    messages = sorted(
        messages,
        key=lambda m: (
            m.date or "",
            str(m.source_id or ""),
            str(m.message_id or ""),
            int((m.metadata or {}).get("row") or 0),
        ),
    )
    detector = RoleDetector(
        RoleDetectorConfig(
            staff_addresses=set(staff_addresses or []),
            staff_domains=set(staff_domains or []),
        )
    )
    warnings: list[str] = []
    if not (staff_addresses or staff_domains):
        warnings.append(
            "staff_addresses / staff_domains が未設定です。"
            "role_hint のないメールは unknown になり、QA ペアが作れない場合があります。"
        )

    cur = conn.execute(
        """
        INSERT INTO imports(source_type, filename, started_at, status)
        VALUES (?, ?, datetime('now'), 'running')
        """,
        (source_type, path.name),
    )
    import_id = int(cur.lastrowid)
    conn.commit()

    total = len(messages)
    new_count = 0
    dup_count = 0
    qa_count = 0
    pending_customer: dict[str, Any] | None = None

    report("dedupe_store", 0.2)
    for idx, message in enumerate(messages, start=1):
        bhash = body_hash(message)
        exists = None
        if message.message_id:
            exists = conn.execute(
                "SELECT id FROM raw_messages WHERE message_id = ?",
                (message.message_id,),
            ).fetchone()
        if exists is None and message.source_id:
            exists = conn.execute(
                "SELECT id FROM raw_messages WHERE source_type = ? AND source_id = ?",
                (source_type, message.source_id),
            ).fetchone()
        if exists is None:
            exists = conn.execute(
                "SELECT id FROM raw_messages WHERE body_hash = ?",
                (bhash,),
            ).fetchone()

        if exists:
            dup_count += 1
            # Keep QA pairing state even when the customer mail was already imported
            role = detector.detect(message)
            cleaned = clean_body(message.body_text, message.body_html)
            if role == "customer" and cleaned:
                pending_customer = {"text": cleaned, "subject": message.subject}
            continue

        cur = conn.execute(
            """
            INSERT INTO raw_messages(source_type, source_id, message_id, payload_json, body_hash, imported_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (source_type, message.source_id, message.message_id, serialize_raw(message), bhash),
        )
        raw_id = int(cur.lastrowid)
        role = detector.detect(message)
        cleaned = clean_body(message.body_text, message.body_html)
        conn.execute(
            """
            INSERT INTO messages(
              raw_message_id, message_id, subject, from_address, to_addresses, cc_addresses,
              date, body_text, body_html, in_reply_to, references_header, source_type, source_id,
              role, body_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                raw_id,
                message.message_id,
                message.subject,
                message.from_address,
                ",".join(message.to_addresses),
                ",".join(message.cc_addresses),
                message.date,
                cleaned,
                message.body_html,
                message.in_reply_to,
                message.references,
                source_type,
                message.source_id,
                role,
                bhash,
            ),
        )
        new_count += 1

        # Naive QA pairing: customer then staff
        if role == "customer":
            pending_customer = {"text": cleaned, "subject": message.subject}
        elif role == "staff" and pending_customer and cleaned:
            pairs = extract_qa_with_rules(pending_customer["text"], cleaned)
            for pair in pairs:
                conn.execute(
                    """
                    INSERT INTO qa_pairs(question, answer, product, confidence, verified, created_at)
                    VALUES (?, ?, ?, ?, 0, datetime('now'))
                    """,
                    (pair["question"], pair["answer"], pending_customer.get("subject"), 0.6),
                )
                qa_count += 1
            pending_customer = None

        if idx % 25 == 0 or idx == total:
            report("dedupe_store", 0.2 + 0.7 * (idx / max(total, 1)))

    conn.execute(
        """
        UPDATE imports
        SET completed_at = datetime('now'),
            total_messages = ?,
            new_messages = ?,
            duplicate_messages = ?,
            qa_count = ?,
            status = 'completed'
        WHERE id = ?
        """,
        (total, new_count, dup_count, qa_count, import_id),
    )
    conn.commit()

    embedded = 0
    embed_status: dict[str, Any] | None = None
    if qa_count > 0 and lancedb_dir is not None:
        report("embedding", 0.92)
        from rag.incremental import embed_new_qa_pairs

        emb = embed_new_qa_pairs(conn, lancedb_dir=lancedb_dir)
        embed_status = emb
        embedded = int(emb.get("embedded") or 0)
        if emb.get("skipped") == "no_api_key":
            warnings.append("Embedding をスキップしました（APIキー未設定）")
        elif embedded == 0 and qa_count > 0:
            warnings.append("Embedding に失敗または未実行です。設定の再構築を確認してください。")

    report("done", 1.0)
    return {
        "import_id": import_id,
        "total_messages": total,
        "new_messages": new_count,
        "duplicate_messages": dup_count,
        "qa_count": qa_count,
        "embedded": embedded,
        "embed_status": embed_status,
        "warnings": warnings,
        "status": "completed",
    }
