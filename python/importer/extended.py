"""Future dump importers: Gmail / Outlook / Zendesk (CSV or MBOX based)."""

from __future__ import annotations

from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter
from importer.csv_importer import CsvImporter
from importer.mbox import MboxImporter


class GmailMboxImporter(MboxImporter):
    """Gmail Takeout mbox."""

    source_type = "gmail_mbox"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages = super().import_file(path)
        for msg in messages:
            msg.source_type = self.source_type
            msg.metadata = {**(msg.metadata or {}), "client": "gmail"}
        return messages


class OutlookCsvImporter(CsvImporter):
    """Outlook exported CSV (flexible headers)."""

    source_type = "outlook_csv"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages = super().import_file(path)
        for msg in messages:
            msg.source_type = self.source_type
            msg.metadata = {**(msg.metadata or {}), "client": "outlook"}
        return messages


class ZendeskCsvImporter(CsvImporter):
    """Zendesk ticket export CSV (mapped via generic CSV aliases)."""

    source_type = "zendesk_csv"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages = super().import_file(path)
        for msg in messages:
            msg.source_type = self.source_type
            msg.metadata = {**(msg.metadata or {}), "client": "zendesk"}
        return messages
