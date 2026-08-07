"""Lightweight row helpers / typed dicts for SQLite entities."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Conversation:
    id: Optional[int] = None
    title: str = ""
    status: str = "active"
    summary: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationMessage:
    id: Optional[int] = None
    conversation_id: int = 0
    role: str = "customer"
    content: str = ""
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QAPair:
    id: Optional[int] = None
    conversation_id: Optional[int] = None
    question: str = ""
    answer: str = ""
    category: Optional[str] = None
    product: Optional[str] = None
    confidence: Optional[float] = None
    verified: bool = False
    source_message_ids: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["verified"] = bool(self.verified)
        return data


@dataclass
class MailMessage:
    message_id: Optional[str] = None
    subject: Optional[str] = None
    from_address: Optional[str] = None
    to_addresses: list[str] = field(default_factory=list)
    cc_addresses: list[str] = field(default_factory=list)
    date: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    source_type: str = "unknown"
    source_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
