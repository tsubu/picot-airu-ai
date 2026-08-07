"""PII masking before sending content to Gemini. RAW must stay unchanged."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:0\d{1,4}[-(]?\d{1,4}[-)]?\d{3,4}|\+?\d[\d\-()]{8,}\d)")
_POSTAL_RE = re.compile(r"〒?\s*\d{3}-?\d{4}")


@dataclass
class PiiMaskConfig:
    mask_email: bool = True
    mask_phone: bool = True
    mask_address: bool = True
    mask_name: bool = False
    mask_order_id: bool = False
    name_patterns: list[str] = field(default_factory=list)


def mask_pii(text: str, config: PiiMaskConfig | None = None) -> str:
    cfg = config or PiiMaskConfig()
    result = text
    if cfg.mask_email:
        result = _EMAIL_RE.sub("[EMAIL]", result)
    if cfg.mask_phone:
        result = _PHONE_RE.sub("[PHONE]", result)
    if cfg.mask_address:
        result = _POSTAL_RE.sub("[ADDRESS]", result)
    if cfg.mask_order_id:
        result = re.sub(r"\b(?:ORD|ORDER)[-_]?\d{4,}\b", "[ORDER]", result, flags=re.I)
    if cfg.mask_name:
        for name in cfg.name_patterns:
            if name:
                result = result.replace(name, "[NAME]")
    return result
