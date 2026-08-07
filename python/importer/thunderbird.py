"""Thunderbird MBOX importer."""

from __future__ import annotations

from pathlib import Path

from database.models import MailMessage
from importer.mbox import MboxImporter


class ThunderbirdImporter(MboxImporter):
    """Thunderbird exports are standard mbox; tag source_type explicitly."""

    source_type = "thunderbird"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages = super().import_file(path)
        for msg in messages:
            msg.source_type = self.source_type
            msg.metadata = {**(msg.metadata or {}), "client": "thunderbird"}
        return messages
