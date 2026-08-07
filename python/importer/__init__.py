"""Importer registry."""

from __future__ import annotations

from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter
from importer.csv_importer import CsvImporter
from importer.eml import EmlImporter
from importer.extended import GmailMboxImporter, OutlookCsvImporter, ZendeskCsvImporter
from importer.maildealer_csv import MailDealerCSVImporter
from importer.mbox import MailDealerMboxImporter, MboxImporter
from importer.thunderbird import ThunderbirdImporter

IMPORTERS: dict[str, type[BaseImporter]] = {
    "maildealer_csv": MailDealerCSVImporter,
    "maildealer_mbox": MailDealerMboxImporter,
    "mbox": MboxImporter,
    "thunderbird": ThunderbirdImporter,
    "eml": EmlImporter,
    "csv": CsvImporter,
    "gmail_mbox": GmailMboxImporter,
    "outlook_csv": OutlookCsvImporter,
    "zendesk_csv": ZendeskCsvImporter,
}


def get_importer(source_type: str) -> BaseImporter:
    try:
        return IMPORTERS[source_type]()
    except KeyError as exc:
        raise ValueError(f"Unsupported source_type: {source_type}") from exc


def import_messages(source_type: str, path: str | Path) -> list[MailMessage]:
    return get_importer(source_type).import_file(Path(path))
