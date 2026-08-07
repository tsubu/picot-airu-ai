"""Customer / Staff role detection. AI assist is last resort (not used in MVP path)."""

from __future__ import annotations

from dataclasses import dataclass, field

from database.models import MailMessage

Role = str  # customer | staff | system | unknown


@dataclass
class RoleDetectorConfig:
    staff_addresses: set[str] = field(default_factory=set)
    staff_domains: set[str] = field(default_factory=set)


def _normalize_addr(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().lower()
    if "<" in text and ">" in text:
        text = text.split("<", 1)[1].split(">", 1)[0]
    return text


def _domain(addr: str | None) -> str | None:
    if not addr or "@" not in addr:
        return None
    return addr.rsplit("@", 1)[-1]


class RoleDetector:
    def __init__(self, config: RoleDetectorConfig | None = None) -> None:
        self.config = config or RoleDetectorConfig()

    def detect(self, message: MailMessage) -> Role:
        hint = (message.metadata or {}).get("role_hint")
        if hint:
            h = str(hint).strip().lower()
            if h in {"customer", "お客様", "受信", "in", "from_customer"}:
                return "customer"
            if h in {"staff", "担当", "送信", "out", "from_staff", "operator"}:
                return "staff"
            if h in {"system", "自動", "noreply"}:
                return "system"

        from_addr = _normalize_addr(message.from_address)
        if from_addr:
            if from_addr in {a.lower() for a in self.config.staff_addresses}:
                return "staff"
            domain = _domain(from_addr)
            if domain and domain in {d.lower() for d in self.config.staff_domains}:
                return "staff"
            if from_addr.startswith(("noreply@", "no-reply@", "mailer-daemon@")):
                return "system"

        # Heuristic: if From is not staff and we have staff domains configured, treat as customer
        if self.config.staff_addresses or self.config.staff_domains:
            return "customer"
        return "unknown"
