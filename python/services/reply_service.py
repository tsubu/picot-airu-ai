"""Reply orchestration service."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ai.providers import build_ai_provider, build_embedding_provider
from ai.reply_generator import generate_reply
from conversation import manager as conv_manager
from conversation.summary import build_extractive_summary, get_summary, upsert_summary
from graph import local_search
from graph.advanced import drift_search
from rag.hybrid_search import HybridSearch
from security.credentials import as_bool, as_float, as_int, get_setting
from security.pii_masker import PiiMaskConfig


def _answer_style(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "company_name": get_setting(conn, "company_name", ""),
        "greeting": get_setting(conn, "greeting", "お問い合わせいただきありがとうございます。"),
        "extra_instructions": get_setting(conn, "extra_instructions", ""),
        "banned_phrases": get_setting(conn, "banned_phrases", ""),
    }


def _provider(conn: sqlite3.Connection):
    return build_ai_provider(conn)


def _enrich_hits_from_graph(
    conn: sqlite3.Connection,
    hits: list[dict[str, Any]],
    graph_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach linked QA from graph as auxiliary context (not primary evidence)."""
    existing = {h.get("qa_id") for h in hits}
    enriched = list(hits)
    for g in graph_hits:
        for qa_id in g.get("qa_ids") or []:
            if qa_id in existing:
                continue
            row = conn.execute(
                "SELECT id, question, answer FROM qa_pairs WHERE id = ?",
                (qa_id,),
            ).fetchone()
            if not row:
                continue
            enriched.append(
                {
                    "qa_id": row["id"],
                    "question": row["question"],
                    "answer": row["answer"],
                    "score": min(0.55, float(g.get("score") or 0.4)),
                    "source": "graph-qa",
                    "evidence": False,
                }
            )
            existing.add(qa_id)
    enriched.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return enriched


def generate_for_new(
    conn: sqlite3.Connection,
    content: str,
    *,
    lancedb_dir: Path,
) -> dict[str, Any]:
    title = conv_manager.make_title_from_text(content)
    conversation = conv_manager.create_conversation(conn, title, content)
    return _generate(conn, conversation["id"], content, lancedb_dir=lancedb_dir, is_new=True)


def generate_for_existing(
    conn: sqlite3.Connection,
    conversation_id: int,
    content: str,
    *,
    lancedb_dir: Path,
) -> dict[str, Any]:
    conv_manager.append_customer_message(conn, conversation_id, content)
    return _generate(conn, conversation_id, content, lancedb_dir=lancedb_dir, is_new=False)


def _generate(
    conn: sqlite3.Connection,
    conversation_id: int,
    content: str,
    *,
    lancedb_dir: Path,
    is_new: bool,
) -> dict[str, Any]:
    recent = conv_manager.recent_context(conn, conversation_id, max_turns=4)
    summary = get_summary(conn, conversation_id)
    if not summary and len(recent) >= 4:
        summary = build_extractive_summary(recent)
        upsert_summary(conn, conversation_id, summary)

    top_k = as_int(get_setting(conn, "rag_top_k", 5), 5)
    min_score = as_float(get_setting(conn, "rag_min_score", 0.25), 0.25)
    use_graph = as_bool(get_setting(conn, "use_graph_rag", True), True)
    allow_offline = as_bool(get_setting(conn, "allow_offline_draft", False), False)
    graph_mode = str(get_setting(conn, "graph_search_mode", "local") or "local").lower()

    search = HybridSearch(conn, lancedb_dir=lancedb_dir, top_k=top_k)
    query = content
    if summary:
        query = f"{summary}\n{content}"

    query_vector = None
    try:
        embedder = build_embedding_provider(conn)
        if embedder is not None:
            model = get_setting(conn, "embedding_model")
            vectors = embedder.embed([query], model=str(model) if model else None)
            if vectors:
                query_vector = vectors[0]
    except Exception:
        query_vector = None

    hits = search.search(query, query_vector=query_vector)

    graph_hits: list[dict[str, Any]] = []
    if use_graph:
        try:
            if graph_mode == "drift":
                graph_hits = drift_search(conn, query, limit=5)
            elif graph_mode == "global":
                from graph.advanced import global_search

                graph_hits = global_search(conn, query, limit=5)
            else:
                graph_hits = local_search(conn, query, limit=5)
            hits = _enrich_hits_from_graph(conn, hits, graph_hits)[:top_k]
        except Exception:
            # Graph is optional; Hybrid continues alone
            graph_hits = []

    pii = PiiMaskConfig(
        mask_email=as_bool(get_setting(conn, "mask_email", True), True),
        mask_phone=as_bool(get_setting(conn, "mask_phone", True), True),
        mask_address=as_bool(get_setting(conn, "mask_address", True), True),
        mask_name=as_bool(get_setting(conn, "mask_name", False), False),
        mask_order_id=as_bool(get_setting(conn, "mask_order_id", False), False),
    )
    provider = _provider(conn)
    model = get_setting(conn, "reply_model", "gemini-2.0-flash")
    result = generate_reply(
        provider,
        customer_message=content,
        conversation_summary=summary,
        recent_messages=recent,
        rag_hits=hits,
        answer_style=_answer_style(conn),
        model=str(model) if model else None,
        min_score=min_score,
        pii_config=pii,
        graph_context=graph_hits,
        allow_offline_draft=allow_offline,
    )

    status = "ok" if result.get("success") else "error"
    conv_manager.append_ai_message(
        conn,
        conversation_id,
        result.get("answer") or result.get("error") or "",
        model=result.get("model") or (str(model) if model else None),
        confidence=result.get("confidence"),
        sources=result.get("sources") or [],
        status=status,
        error_message=result.get("error"),
    )
    conversation = conv_manager.get_conversation(conn, conversation_id)
    ok = bool(result.get("success"))
    return {
        "success": ok,
        "error": result.get("error"),
        "conversation": conversation,
        "answer": result.get("answer"),
        "confidence": result.get("confidence"),
        "sources": result.get("sources") or [],
        "graph_hits": result.get("graph_hits") or [],
        "insufficient_evidence": result.get("insufficient_evidence", False),
        "is_new": is_new,
        "vector_search": query_vector is not None,
    }
