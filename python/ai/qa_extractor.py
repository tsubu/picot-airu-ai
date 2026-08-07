"""QA extraction from staff conversations."""

from __future__ import annotations

import json
import re
from typing import Any

from ai.gemini import AIProvider


def extract_qa_with_rules(customer_text: str, staff_text: str) -> list[dict[str, str]]:
    """Simple fallback: one QA from a customer/staff pair."""
    q = customer_text.strip()
    a = staff_text.strip()
    if not q or not a:
        return []
    return [{"question": q, "answer": a}]


def extract_qa_with_gemini(provider: AIProvider, customer_text: str, staff_text: str, *, model: str | None) -> list[dict[str, Any]]:
    prompt = f"""次の顧客メールとスタッフ返信から、独立したQAペアをJSON配列で抽出してください。
各要素は {{"question": "...", "answer": "..."}} 形式。
推測で補完しないでください。根拠のないQAは作らないでください。

Customer:
{customer_text}

Staff:
{staff_text}
"""
    raw = provider.generate(prompt, model=model)
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        return extract_qa_with_rules(customer_text, staff_text)
    try:
        data = json.loads(match.group(0))
        result = []
        for item in data:
            if isinstance(item, dict) and item.get("question") and item.get("answer"):
                result.append({"question": str(item["question"]), "answer": str(item["answer"])})
        return result or extract_qa_with_rules(customer_text, staff_text)
    except json.JSONDecodeError:
        return extract_qa_with_rules(customer_text, staff_text)
