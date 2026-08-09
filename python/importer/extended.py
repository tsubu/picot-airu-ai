"""Dump importers: Gmail / Outlook / Zendesk (CSV or MBOX based)."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter
from importer.csv_headers import pick_field
from importer.csv_importer import CsvImporter
from importer.mbox import MboxImporter

_OUTLOOK_ALIASES = {
    "source_id": ("entry id", "conversation id", "internet message id", "id"),
    "message_id": ("internet message id", "message-id", "message id", "entry id"),
    "subject": ("subject", "件名"),
    "from_address": (
        "from: (address)",
        "from (address)",
        "from address",
        "from",
        "sender address",
        "差出人",
        "送信元",
    ),
    "from_name": ("from: (name)", "from (name)", "from name", "sender name"),
    "to_addresses": (
        "to: (address)",
        "to (address)",
        "to address",
        "to",
        "recipient address",
        "宛先",
        "送信先",
    ),
    "date": (
        "sent",
        "sent on",
        "received",
        "received time",
        "message delivery time",
        "作成日時",
        "送信日時",
        "date",
    ),
    "body_text": ("body", "body content", "message", "本文", "内容"),
    "categories": ("categories", "category", "folder", "folders", "フォルダー", "分類項目"),
    "role": ("role", "roles", "方向", "送受信", "type"),
}

_ZENDESK_ALIASES = {
    "ticket_id": ("ticket id", "ticket_id", "id", "チケットID"),
    "subject": ("subject", "title", "件名", "タイトル"),
    "requester": (
        "requester",
        "requester email",
        "requester name",
        "submitter",
        "依頼者",
        "requester id",
    ),
    "assignee": ("assignee", "assignee email", "assignee name", "担当者"),
    "created": ("created at", "created", "requested at", "作成日時", "date"),
    "comment_created": ("comment created at", "commented at", "updated at"),
    "body_text": (
        "comment",
        "public comment",
        "description",
        "body",
        "details",
        "本文",
        "内容",
        "コメント",
    ),
    "author": ("comment author", "author", "author name", "author email", "from"),
    "is_public": ("is public", "public", "公開"),
}


def _split_addresses(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[;,]", raw)
    return [p.strip() for p in parts if p.strip()]


def _looks_like_email(value: str | None) -> bool:
    return bool(value and "@" in value)


def _outlook_role_hint(
    *,
    from_addr: str | None,
    to_addresses: list[str],
    categories: str | None,
    role_field: str | None,
) -> str | None:
    if role_field:
        r = role_field.strip().lower()
        if r in {"customer", "お客様", "受信", "in", "incoming", "from_customer"}:
            return "customer"
        if r in {"staff", "担当", "送信", "out", "outgoing", "from_staff", "operator"}:
            return "staff"

    if categories:
        cl = categories.strip().lower()
        if any(x in cl for x in ("sent items", "sent", "送信済み", "送信", "outbox", "outgoing")):
            return "staff"
        if any(x in cl for x in ("inbox", "受信トレイ", "受信", "incoming")):
            return "customer"

    from_l = (from_addr or "").strip().lower()
    if from_l.startswith(("support@", "help@", "cs@", "info@", "noreply@", "no-reply@")):
        return "staff"
    if any(
        t.strip().lower().startswith(("support@", "help@", "cs@")) for t in to_addresses
    ) and from_l and "@" in from_l:
        return "customer"
    return None


class GmailMboxImporter(MboxImporter):
    """Gmail Takeout mbox."""

    source_type = "gmail_mbox"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages = super().import_file(path)
        for msg in messages:
            msg.source_type = self.source_type
            msg.metadata = {**(msg.metadata or {}), "client": "gmail"}
        return messages


class OutlookCsvImporter(BaseImporter):
    """Outlook / Microsoft 365 exported CSV (common English headers)."""

    source_type = "outlook_csv"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages: list[MailMessage] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                from_addr = pick_field(row, _OUTLOOK_ALIASES["from_address"])
                from_name = pick_field(row, _OUTLOOK_ALIASES["from_name"])
                if not _looks_like_email(from_addr) and _looks_like_email(from_name):
                    from_addr, from_name = from_name, from_addr
                if not from_addr and from_name:
                    from_addr = from_name

                to_raw = pick_field(row, _OUTLOOK_ALIASES["to_addresses"]) or ""
                to_addresses = _split_addresses(to_raw)
                source_id = (
                    pick_field(row, _OUTLOOK_ALIASES["source_id"])
                    or pick_field(row, _OUTLOOK_ALIASES["message_id"])
                    or f"{path.name}:{idx}"
                )
                categories = pick_field(row, _OUTLOOK_ALIASES["categories"])
                role_field = pick_field(row, _OUTLOOK_ALIASES["role"])
                role_hint = _outlook_role_hint(
                    from_addr=from_addr,
                    to_addresses=to_addresses,
                    categories=categories,
                    role_field=role_field,
                )
                messages.append(
                    MailMessage(
                        message_id=pick_field(row, _OUTLOOK_ALIASES["message_id"]),
                        subject=pick_field(row, _OUTLOOK_ALIASES["subject"]),
                        from_address=from_addr,
                        to_addresses=to_addresses,
                        date=pick_field(row, _OUTLOOK_ALIASES["date"]),
                        body_text=pick_field(row, _OUTLOOK_ALIASES["body_text"]) or "",
                        source_type=self.source_type,
                        source_id=source_id,
                        metadata={
                            "client": "outlook",
                            "from_name": from_name,
                            "role_hint": role_hint,
                            "categories": categories,
                            "row": idx,
                        },
                    )
                )
        return messages


class ZendeskCsvImporter(BaseImporter):
    """Zendesk ticket/comment export CSV.

    Supports:
    - one row per ticket (Description)
    - one row per comment (Ticket ID + Comment + Author)
    """

    source_type = "zendesk_csv"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages: list[MailMessage] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                ticket_id = pick_field(row, _ZENDESK_ALIASES["ticket_id"]) or f"{path.name}:{idx}"
                subject = pick_field(row, _ZENDESK_ALIASES["subject"]) or f"Ticket {ticket_id}"
                body = pick_field(row, _ZENDESK_ALIASES["body_text"]) or ""
                if not body.strip():
                    continue

                author = pick_field(row, _ZENDESK_ALIASES["author"])
                requester = pick_field(row, _ZENDESK_ALIASES["requester"])
                assignee = pick_field(row, _ZENDESK_ALIASES["assignee"])
                from_addr = author or requester or "unknown@zendesk.local"
                to_addr = assignee or "support@zendesk.local"

                # Heuristic role hint: assignee-looking author => staff
                role_hint = None
                if author and assignee and author.lower() == assignee.lower():
                    role_hint = "staff"
                elif author and requester and author.lower() == requester.lower():
                    role_hint = "customer"
                elif assignee and from_addr.lower() == assignee.lower():
                    role_hint = "staff"
                elif requester and from_addr.lower() == requester.lower():
                    role_hint = "customer"

                date = (
                    pick_field(row, _ZENDESK_ALIASES["comment_created"])
                    or pick_field(row, _ZENDESK_ALIASES["created"])
                )
                source_id = f"{ticket_id}:{idx}"
                messages.append(
                    MailMessage(
                        message_id=f"<zendesk-{ticket_id}-{idx}@local>",
                        subject=subject,
                        from_address=from_addr,
                        to_addresses=_split_addresses(to_addr),
                        date=date,
                        body_text=body,
                        source_type=self.source_type,
                        source_id=source_id,
                        metadata={
                            "client": "zendesk",
                            "ticket_id": ticket_id,
                            "role_hint": role_hint,
                            "row": idx,
                        },
                    )
                )
        return messages


# Keep CsvImporter import used for typing/compat in older call sites
__all__ = [
    "GmailMboxImporter",
    "OutlookCsvImporter",
    "ZendeskCsvImporter",
    "CsvImporter",
]
