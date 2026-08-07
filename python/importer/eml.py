"""Single EML file or directory of EML files importer."""

from __future__ import annotations

import email
from email.header import decode_header, make_header
from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter
from importer.mbox import _addresses, _body_text


def _decode(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


class EmlImporter(BaseImporter):
    source_type = "eml"

    def import_file(self, path: Path) -> list[MailMessage]:
        path = Path(path)
        files: list[Path]
        if path.is_dir():
            files = sorted(path.glob("*.eml"))
        else:
            files = [path]

        messages: list[MailMessage] = []
        for idx, file_path in enumerate(files, start=1):
            raw = file_path.read_bytes()
            msg = email.message_from_bytes(raw)
            text_body, html_body = _body_text(msg)
            message_id = _decode(msg.get("Message-ID"))
            messages.append(
                MailMessage(
                    message_id=message_id,
                    subject=_decode(msg.get("Subject")),
                    from_address=_decode(msg.get("From")),
                    to_addresses=_addresses(msg, "To"),
                    cc_addresses=_addresses(msg, "Cc"),
                    date=_decode(msg.get("Date")),
                    body_text=text_body,
                    body_html=html_body,
                    in_reply_to=_decode(msg.get("In-Reply-To")),
                    references=_decode(msg.get("References")),
                    source_type=self.source_type,
                    source_id=message_id or f"{file_path.name}:{idx}",
                    metadata={"filename": file_path.name},
                )
            )
        return messages
