"""Importer base interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from database.models import MailMessage


class BaseImporter(ABC):
    source_type: str = "unknown"

    @abstractmethod
    def import_file(self, path: Path) -> list[MailMessage]:
        raise NotImplementedError
