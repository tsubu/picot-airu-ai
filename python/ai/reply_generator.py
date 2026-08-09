"""Reply generation with RAG context. Never writes AI answers into QA knowledge."""

from __future__ import annotations

from typing import Any

from ai.gemini import AIProvider
from security.pii_masker import PiiMaskConfig, mask_pii

SYSTEM_RULES = """あなたは企業サポート担当の返信案作成アシスタントです。
- 過去ナレッジを優先する
- 提供された根拠にない情報を推測しない
- 確証がない内容を断定しない
- 顧客向けメールとして自然な文章にする
- 過去スタッフ回答をそのままコピーせず、今回の問い合わせに合わせて再構成する
- 企業固有の事実について一般知識だけで断定しない
"""


def _mask_text(text: str | None, config: PiiMaskConfig | None) -> str:
    return mask_pii(text or "", config)


def _mask_recent(
    recent_messages: list[dict[str, str]],
    config: PiiMaskConfig | None,
) -> list[dict[str, str]]:
    return [
        {"role": m.get("role") or "customer", "content": _mask_text(m.get("content"), config)}
        for m in recent_messages
    ]


def _mask_rag_hits(
    rag_hits: list[dict[str, Any]],
    config: PiiMaskConfig | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hit in rag_hits:
        row = dict(hit)
        if "question" in row:
            row["question"] = _mask_text(str(row.get("question") or ""), config)
        if "answer" in row:
            row["answer"] = _mask_text(str(row.get("answer") or ""), config)
        out.append(row)
    return out


def _mask_graph(
    graph_context: list[dict[str, Any]] | None,
    config: PiiMaskConfig | None,
) -> list[dict[str, Any]] | None:
    if not graph_context:
        return graph_context
    out: list[dict[str, Any]] = []
    for g in graph_context:
        row = dict(g)
        if "name" in row:
            row["name"] = _mask_text(str(row.get("name") or ""), config)
        neighbors = []
        for n in row.get("neighbors") or []:
            nn = dict(n)
            if "name" in nn:
                nn["name"] = _mask_text(str(nn.get("name") or ""), config)
            neighbors.append(nn)
        if "neighbors" in row:
            row["neighbors"] = neighbors
        out.append(row)
    return out


def build_reply_prompt(
    *,
    customer_message: str,
    conversation_summary: str | None,
    recent_messages: list[dict[str, str]],
    rag_hits: list[dict[str, Any]],
    answer_style: dict[str, Any],
    graph_context: list[dict[str, Any]] | None = None,
) -> str:
    recent_block = "\n".join(
        f"{'Customer' if m['role'] == 'customer' else 'AI'}: {m['content']}" for m in recent_messages
    )
    rag_block = "\n\n".join(
        f"QA#{h.get('qa_id')}\nQ: {h.get('question')}\nA: {h.get('answer')}\nscore={h.get('score')}"
        for h in rag_hits
    ) or "(該当なし)"
    graph_block = "(なし)"
    if graph_context:
        lines = []
        for g in graph_context:
            neigh = ", ".join(
                f"{n.get('relation_type')}:{n.get('name')}" for n in (g.get("neighbors") or [])[:5]
            )
            lines.append(
                f"{g.get('entity_type')}:{g.get('name')} score={g.get('score')} neighbors=[{neigh}]"
            )
        graph_block = "\n".join(lines)
    company = answer_style.get("company_name") or ""
    greeting = answer_style.get("greeting") or "お問い合わせいただきありがとうございます。"
    extra = answer_style.get("extra_instructions") or ""
    banned = answer_style.get("banned_phrases") or ""
    return f"""{SYSTEM_RULES}

会社名: {company}
基本挨拶: {greeting}
追加指示: {extra}
禁止表現: {banned}

Conversation Summary:
{conversation_summary or '(なし)'}

直近のやり取り:
{recent_block or '(なし)'}

今回の顧客メール:
{customer_message}

参考過去QA:
{rag_block}

Graph Knowledge（補助・未構築なら無視）:
{graph_block}

上記のみを根拠に、顧客への返信案本文だけを出力してください。
"""


def generate_reply(
    provider: AIProvider | None,
    *,
    customer_message: str,
    conversation_summary: str | None,
    recent_messages: list[dict[str, str]],
    rag_hits: list[dict[str, Any]],
    answer_style: dict[str, Any],
    model: str | None,
    min_score: float,
    pii_config: PiiMaskConfig | None = None,
    graph_context: list[dict[str, Any]] | None = None,
    allow_offline_draft: bool = False,
) -> dict[str, Any]:
    strong_hits = [
        h
        for h in rag_hits
        if float(h.get("score") or 0) >= min_score
        and h.get("source") != "graph-qa"
        and h.get("evidence", True) is not False
    ]
    # Graph alone does not satisfy evidence; Hybrid QA hits remain primary.
    if not strong_hits:
        return {
            "success": True,
            "insufficient_evidence": True,
            "answer": (
                "十分な過去対応データが見つかりませんでした。\n"
                "内容を確認した上で、手動で対応してください。"
            ),
            "confidence": 0.0,
            "sources": [],
            "graph_hits": graph_context or [],
        }

    masked_customer = _mask_text(customer_message, pii_config)
    masked_summary = (
        _mask_text(conversation_summary, pii_config) if conversation_summary else None
    )
    masked_recent = _mask_recent(recent_messages, pii_config)
    masked_hits = _mask_rag_hits(strong_hits, pii_config)
    masked_graph = _mask_graph(graph_context, pii_config)

    prompt = build_reply_prompt(
        customer_message=masked_customer,
        conversation_summary=masked_summary,
        recent_messages=masked_recent,
        rag_hits=masked_hits,
        answer_style=answer_style,
        graph_context=masked_graph,
    )
    if provider is None:
        if not allow_offline_draft:
            return {
                "success": False,
                "insufficient_evidence": False,
                "error": "AIプロバイダが未設定です。設定画面でAPIキーを登録するか、開発用オフライン下書きを有効にしてください。",
                "answer": "",
                "confidence": 0.0,
                "sources": [
                    {"qa_id": h.get("qa_id"), "score": h.get("score")} for h in strong_hits
                ],
                "graph_hits": graph_context or [],
            }
        # Offline/dev fallback: paraphrase top answer without inventing facts
        top = strong_hits[0]
        answer = (
            f"{answer_style.get('greeting') or 'お問い合わせいただきありがとうございます。'}\n\n"
            f"{_mask_text(str(top.get('answer') or ''), pii_config)}\n\n"
            "※開発モード: AI未接続のため過去回答を再構成した下書きです。"
        )
        return {
            "success": True,
            "insufficient_evidence": False,
            "answer": answer,
            "confidence": float(top.get("score") or 0.5),
            "sources": [
                {"qa_id": h.get("qa_id"), "score": h.get("score")} for h in strong_hits
            ],
            "graph_hits": graph_context or [],
            "model": "offline-fallback",
        }

    answer = provider.generate(prompt, model=model)
    avg = sum(float(h.get("score") or 0) for h in strong_hits) / len(strong_hits)
    return {
        "success": True,
        "insufficient_evidence": False,
        "answer": answer.strip(),
        "confidence": avg,
        "sources": [{"qa_id": h.get("qa_id"), "score": h.get("score")} for h in strong_hits],
        "graph_hits": graph_context or [],
        "model": model,
    }
