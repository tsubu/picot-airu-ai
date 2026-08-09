"""CSV header helpers shared by Mail Dealer / Outlook / Zendesk importers."""

from __future__ import annotations

import re


def normalize_header(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("：", ":")
    text = re.sub(r"\s+", " ", text)
    return text


def header_key_variants(value: str) -> set[str]:
    """Return lookup keys for a CSV header (raw + normalized + paren-stripped)."""
    raw = (value or "").strip()
    norm = normalize_header(raw)
    keys = {raw.lower(), norm}
    # Outlook often uses "From: (Name)" / "To: (Address)"
    stripped = re.sub(r"[\s:]+", " ", norm)
    keys.add(stripped)
    no_paren = re.sub(r"\([^)]*\)", "", norm).strip()
    keys.add(no_paren)
    keys.add(re.sub(r"[\s:]+", "", norm))
    return {k for k in keys if k}


def pick_field(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    """Pick a value from a CSV row using flexible header aliases."""
    lookup: dict[str, str] = {}
    for header, value in row.items():
        if header is None:
            continue
        for variant in header_key_variants(str(header)):
            lookup[variant] = "" if value is None else str(value)

    for key in keys:
        for variant in header_key_variants(key):
            if variant in lookup and lookup[variant].strip() != "":
                return lookup[variant].strip()
    return None
