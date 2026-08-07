"""Mail RAG Desktop — Python package root helpers."""

from __future__ import annotations

from pathlib import Path

from paths import default_workspace_root

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent

__all__ = ["PACKAGE_ROOT", "REPO_ROOT", "default_workspace_root"]
