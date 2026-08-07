"""Generic CSV importer with flexible headers."""

from __future__ import annotations

import csv
from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter
from importer.maildealer_csv import _ALIASES, _pick


class CsvImporter(BaseImporter):
    source_type = "csv"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages: list[MailMessage] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                source_id = _pick(row, _ALIASES["source_id"]) or f"{path.name}:{idx}"
                to_raw = _pick(row, _ALIASES["to_addresses"]) or ""
                messages.append(
                    MailMessage(
                        message_id=_pick(row, _ALIASES["message_id"]),
                        subject=_pick(row, _ALIASES["subject"]),
                        from_address=_pick(row, _ALIASES["from_address"]),
                        to_addresses=[p.strip() for p in to_raw.split(",") if p.strip()],
                        date=_pick(row, _ALIASES["date"]),
                        body_text=_pick(row, _ALIASES["body_text"]) or "",
                        source_type=self.source_type,
                        source_id=source_id,
                        metadata={"role_hint": _pick(row, _ALIASES["role"]), "row": idx},
                    )
                )
        return messages
