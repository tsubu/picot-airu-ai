"""Application paths and workspace bootstrap."""

from __future__ import annotations

from pathlib import Path


def default_workspace_root() -> Path:
    """Return the default local workspace path (~/MailRAG)."""
    return Path.home() / "MailRAG"


def ensure_workspace(root: Path | None = None) -> Path:
    """Create MailRAG workspace directories if missing and return root."""
    base = root or default_workspace_root()
    for rel in (
        "config",
        "workspace",
        "workspace/imports",
        "workspace/raw",
        "workspace/lancedb",
        "workspace/exports",
        "workspace/backup",
        "logs",
    ):
        (base / rel).mkdir(parents=True, exist_ok=True)
    return base


def sqlite_path(root: Path | None = None) -> Path:
    base = ensure_workspace(root)
    return base / "workspace" / "mailrag.sqlite3"


def lancedb_path(root: Path | None = None) -> Path:
    base = ensure_workspace(root)
    return base / "workspace" / "lancedb"


def logs_path(root: Path | None = None) -> Path:
    base = ensure_workspace(root)
    return base / "logs"
