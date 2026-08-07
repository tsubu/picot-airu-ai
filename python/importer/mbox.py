"""Generic / Mail Dealer MBOX importer."""

from __future__ import annotations

import email
import mailbox
from email.header import decode_header, make_header
from pathlib import Path

from database.models import MailMessage
from importer.base import BaseImporter


def _decode(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _addresses(msg: email.message.Message, header: str) -> list[str]:
    raw = msg.get(header)
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _body_text(msg: email.message.Message) -> tuple[str | None, str | None]:
    text_body = None
    html_body = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and text_body is None:
                text_body = decoded
            elif ctype == "text/html" and html_body is None:
                html_body = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload is not None:
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_body = decoded
                else:
                    text_body = decoded
        except Exception:
            pass
    return text_body, html_body


class MboxImporter(BaseImporter):
    source_type = "mbox"

    def import_file(self, path: Path) -> list[MailMessage]:
        messages: list[MailMessage] = []
        mbox = mailbox.mbox(str(path))
        for idx, msg in enumerate(mbox, start=1):
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
                    source_id=message_id or f"{path.name}:{idx}",
                    metadata={},
                )
            )
        return messages


class MailDealerMboxImporter(MboxImporter):
    source_type = "maildealer_mbox"
