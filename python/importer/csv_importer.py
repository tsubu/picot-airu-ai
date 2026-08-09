"""Generic CSV importer with flexible headers."""

from __future__ import annotations

import csv
from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter
from importer.csv_headers import pick_field
from importer.maildealer_csv import _ALIASES


class CsvImporter(BaseImporter):
    source_type = "csv"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages: list[MailMessage] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                source_id = pick_field(row, _ALIASES["source_id"]) or f"{path.name}:{idx}"
                to_raw = pick_field(row, _ALIASES["to_addresses"]) or ""
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
                        metadata={"role_hint": pick_field(row, _ALIASES["role"]), "row": idx},
                    )
                )
        return messages
