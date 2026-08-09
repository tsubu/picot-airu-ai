"""Mail Dealer CSV importer (anonymized / flexible column mapping)."""

from __future__ import annotations

import csv
from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter
from importer.csv_headers import pick_field

# Flexible header aliases seen in Mail Dealer exports / samples
_ALIASES = {
    "source_id": ("mail_id", "id", "メールID", "対応ID"),
    "message_id": ("message_id", "message-id", "Message-ID"),
    "subject": ("subject", "件名", "タイトル"),
    "from_address": ("from", "from_address", "送信元", "差出人"),
    "to_addresses": ("to", "to_address", "送信先", "宛先"),
    "date": ("date", "datetime", "受信日時", "送信日時", "日時"),
    "body_text": ("body", "body_text", "本文", "内容"),
    "role": ("role", "送受信", "区分", "direction"),
}


# Back-compat for older imports
def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    return pick_field(row, keys)


class MailDealerCSVImporter(BaseImporter):
    source_type = "maildealer_csv"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages: list[MailMessage] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                source_id = pick_field(row, _ALIASES["source_id"]) or f"{path.name}:{idx}"
                to_raw = pick_field(row, _ALIASES["to_addresses"]) or ""
                role_hint = pick_field(row, _ALIASES["role"])
                messages.append(
                    MailMessage(
                        message_id=pick_field(row, _ALIASES["message_id"]),
                        subject=pick_field(row, _ALIASES["subject"]),
                        from_address=pick_field(row, _ALIASES["from_address"]),
                        to_addresses=[p.strip() for p in to_raw.split(",") if p.strip()],
                        date=pick_field(row, _ALIASES["date"]),
                        body_text=pick_field(row, _ALIASES["body_text"]) or "",
                        source_type=self.source_type,
                        source_id=source_id,
                        metadata={"role_hint": role_hint, "row": idx},
                    )
                )
        return messages
