"""Mail body cleaning. RAW data must remain unchanged elsewhere."""

from __future__ import annotations

import re

_HTML_RE = re.compile(r"<[^>]+>")
_QUOTE_RE = re.compile(r"(?m)^>.*$")
_TRACKING_RE = re.compile(r"https?://\S*(?:track|click|unsubscribe)\S*", re.I)
_SIGNATURE_MARKERS = (
    "\n-- \n",
    "\n――――――――――――――――――――\n",
    "\n********************************\n",
)


def strip_html(html: str) -> str:
    text = _HTML_RE.sub(" ", html)
    return re.sub(r"\s+", " ", text).strip()


def clean_body(text: str | None, html: str | None = None) -> str:
    source = text or (strip_html(html) if html else "")
    if not source:
        return ""
    cleaned = _QUOTE_RE.sub("", source)
    cleaned = _TRACKING_RE.sub("", cleaned)
    for marker in _SIGNATURE_MARKERS:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0]
    # Common Japanese mobile/mailer quoted reply header
    cleaned = re.split(r"\n[-]{2,}\s*Original Message\s*[-]{2,}\n", cleaned, maxsplit=1)[0]
    cleaned = re.split(r"\nFrom: .+\nSent: .+\n", cleaned, maxsplit=1)[0]
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
