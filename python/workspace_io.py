"""Workspace export / import (no API keys)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from database.sqlite import migrate
from paths import ensure_workspace, lancedb_path, sqlite_path
from security.credentials import get_setting


EXPORT_SETTINGS_ALLOWLIST = {
    "company_name",
    "greeting",
    "extra_instructions",
    "banned_phrases",
    "reply_model",
    "qa_model",
    "embedding_model",
    "rag_top_k",
    "rag_min_score",
    "mask_email",
    "mask_phone",
    "mask_address",
    "mask_name",
    "mask_order_id",
    "use_graph_rag",
    "staff_addresses",
    "staff_domains",
    "ai_provider",
    "openai_base_url",
    "claude_base_url",
    "ollama_base_url",
    "ollama_model",
    "ui_locale",
    "faq_snapshot",
}


def export_workspace(root: Path | None = None) -> dict[str, Any]:
    base = ensure_workspace(root)
    exports = base / "workspace" / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = exports / f"mailrag_workspace_{stamp}.zip"
    db = sqlite_path(base)
    lance = lancedb_path(base)

    meta: dict[str, Any] = {
        "exported_at": stamp,
        "includes": ["mailrag.sqlite3", "settings_safe.json"],
        "has_lancedb": lance.exists(),
    }
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        settings = {}
        for row in conn.execute("SELECT key, value FROM settings").fetchall():
            if row["key"] in EXPORT_SETTINGS_ALLOWLIST:
                settings[row["key"]] = row["value"]
        meta["settings_keys"] = sorted(settings.keys())

    safe_settings_path = exports / f"_settings_{stamp}.json"
    safe_settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path = exports / f"_meta_{stamp}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(db, arcname="mailrag.sqlite3")
        zf.write(safe_settings_path, arcname="settings_safe.json")
        zf.write(meta_path, arcname="meta.json")
        if lance.exists():
            for path in lance.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(Path("lancedb") / path.relative_to(lance)))

    safe_settings_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    return {"success": True, "path": str(out), "meta": meta}


def _safe_extractall(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract ZIP members while preventing Zip Slip path traversal."""
    dest = dest.resolve()
    for info in zf.infolist():
        name = info.filename
        if not name or name.endswith("/"):
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest) + "/") and target != dest:
                raise ValueError(f"unsafe zip path: {name}")
            target.mkdir(parents=True, exist_ok=True)
            continue
        target = (dest / name).resolve()
        if not str(target).startswith(str(dest) + "/"):
            raise ValueError(f"unsafe zip path: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def import_workspace(zip_path: str | Path, root: Path | None = None) -> dict[str, Any]:
    base = ensure_workspace(root)
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return {"success": False, "error": f"file not found: {zip_path}"}

    staging = base / "workspace" / "imports" / f"workspace_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extractall(zf, staging)
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        return {"success": False, "error": f"ZIP 展開に失敗しました: {exc}"}

    src_db = staging / "mailrag.sqlite3"
    if not src_db.exists():
        return {"success": False, "error": "mailrag.sqlite3 が ZIP に含まれていません"}

    dest_db = sqlite_path(base)
    backup = dest_db.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    if dest_db.exists():
        shutil.copy2(dest_db, backup)
    shutil.copy2(src_db, dest_db)
    migrate(dest_db)

    # restore allowlisted settings from snapshot if present
    settings_file = staging / "settings_safe.json"
    restored = 0
    if settings_file.exists():
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        with sqlite3.connect(str(dest_db)) as conn:
            for key, value in data.items():
                if key not in EXPORT_SETTINGS_ALLOWLIST:
                    continue
                if key in {"gemini_api_key", "api_key", "openai_api_key", "claude_api_key"}:
                    continue
                conn.execute(
                    """
                    INSERT INTO settings(key, value, updated_at)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')
                    """,
                    (key, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)),
                )
                restored += 1
            conn.commit()

    lance_src = staging / "lancedb"
    if lance_src.exists():
        lance_dest = lancedb_path(base)
        if lance_dest.exists():
            shutil.rmtree(lance_dest)
        shutil.copytree(lance_src, lance_dest)

    return {
        "success": True,
        "backup_db": str(backup) if backup.exists() else None,
        "restored_settings": restored,
        "staging": str(staging),
    }
