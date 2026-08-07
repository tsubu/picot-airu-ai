"""Duplicate detection helpers."""

from __future__ import annotations

import hashlib
import json

from database.models import MailMessage


def body_hash(message: MailMessage) -> str:
    body = (message.body_text or message.body_html or "").strip()
    basis = "|".join(
        [
            message.message_id or "",
            message.source_id or "",
            message.date or "",
            (message.from_address or "").lower(),
            (message.subject or "").strip(),
            body,
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def duplicate_keys(message: MailMessage) -> dict[str, str | None]:
    return {
        "message_id": message.message_id,
        "source_id": message.source_id,
        "body_hash": body_hash(message),
    }


def serialize_raw(message: MailMessage) -> str:
    return json.dumps(message.to_dict(), ensure_ascii=False)
