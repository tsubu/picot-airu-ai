"""JSON HTTP sidecar for Mail RAG Desktop."""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Ensure python/ is on path when executed as script
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_logging import log_event  # noqa: E402
from conversation import manager as conv_manager  # noqa: E402
from database.sqlite import connect, migrate  # noqa: E402
from paths import ensure_workspace, lancedb_path, sqlite_path  # noqa: E402
from security.credentials import (  # noqa: E402
    SECRET_SETTING_KEYS,
    as_str_list,
    delete_api_key,
    get_api_key,
    get_setting,
    set_api_key,
    set_setting,
)
from services.import_service import run_import  # noqa: E402
from services.data_reset import reset_imported_data  # noqa: E402
from services.reply_service import generate_for_existing, generate_for_new  # noqa: E402
from graph import graph_stats, rebuild_graph, trend_analysis  # noqa: E402
from graph.advanced import (  # noqa: E402
    drift_search,
    generate_faqs,
    global_search,
    knowledge_analysis,
)
from rag.rebuild import rebuild_embeddings  # noqa: E402
from workspace_io import export_workspace, import_workspace  # noqa: E402
from ai.providers import (  # noqa: E402
    build_ai_provider,
    get_claude_api_key,
    get_openai_api_key,
    list_provider_models,
    provider_auth_status,
    set_claude_api_key,
    set_openai_api_key,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765


class AppState:
    def __init__(self) -> None:
        self.workspace = ensure_workspace()
        self.db_path = sqlite_path(self.workspace)
        migrate(self.db_path)
        self.lancedb_dir = lancedb_path(self.workspace)
        self.progress: dict[str, Any] = {"stage": "idle", "percent": 0.0}

    def conn(self):
        return connect(self.db_path)


STATE = AppState()


def handle_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "health":
        with STATE.conn() as conn:
            auth = provider_auth_status(conn)
        return {
            "success": True,
            "status": "ok",
            "workspace": str(STATE.workspace),
            "has_api_key": bool(get_api_key()),
            "has_openai_api_key": bool(get_openai_api_key()),
            "has_claude_api_key": bool(get_claude_api_key()),
            "provider_auth": auth,
        }

    if action == "set_api_key":
        key = (payload.get("api_key") or "").strip()
        if not key:
            return {"success": False, "error": "api_key is required"}
        set_api_key(key)
        with STATE.conn() as conn:
            log_event(conn, "info", "api_key_updated")
        return {"success": True}

    if action == "clear_api_key":
        delete_api_key()
        return {"success": True}

    if action == "test_api_key":
        # Prefer testing the currently selected provider.
        with STATE.conn() as conn:
            auth = provider_auth_status(conn)
            provider_name = auth.get("provider") or "gemini"
            if not auth.get("ready"):
                return {
                    "success": False,
                    "error_code": "missing_api_key",
                    "error": auth.get("message") or "APIキーが設定されていません",
                }
            try:
                provider = build_ai_provider(conn)
                if provider is None:
                    return {
                        "success": False,
                        "error_code": "missing_api_key",
                        "error": "APIキーが設定されていません",
                    }
                model = get_setting(conn, "reply_model")
                text = provider.generate("Reply with OK only.", model=str(model) if model else None)
                return {
                    "success": True,
                    "provider": provider_name,
                    "message": text[:200],
                }
            except Exception as exc:
                from ai.providers import classify_provider_error

                mapped = classify_provider_error(exc)
                return {"success": False, **mapped}

    if action == "refresh_models":
        key = get_api_key()
        if not key:
            return {"success": False, "error": "APIキーが設定されていません"}
        try:
            from datetime import datetime, timezone

            from ai.gemini import filter_models, list_gemini_models

            catalog = list_gemini_models(key)
            reply_models = filter_models(catalog, "generate")
            embedding_models = filter_models(catalog, "embed")
            fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            with STATE.conn() as conn:
                set_setting(conn, "gemini_model_catalog", catalog)
                set_setting(conn, "gemini_reply_models", reply_models)
                set_setting(conn, "gemini_embedding_models", embedding_models)
                set_setting(conn, "gemini_models_fetched_at", fetched_at)
                current_reply = get_setting(conn, "reply_model")
                ids = {m["id"] for m in reply_models}
                if current_reply not in ids and reply_models:
                    set_setting(conn, "reply_model", reply_models[0]["id"])
                log_event(
                    conn,
                    "info",
                    "models_refreshed",
                    {"generate": len(reply_models), "embed": len(embedding_models)},
                )
                selected = get_setting(conn, "reply_model", "gemini-2.0-flash")
            return {
                "success": True,
                "reply_models": reply_models,
                "embedding_models": embedding_models,
                "models_fetched_at": fetched_at,
                "reply_model": selected,
            }
        except Exception as exc:
            return {"success": False, "error": f"モデル一覧の取得に失敗しました: {exc}"}

    if action == "get_settings":
        with STATE.conn() as conn:
            keys = [
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
                "graph_search_mode",
                "ai_provider",
                "embedding_provider",
                "openai_base_url",
                "claude_base_url",
                "ollama_base_url",
                "ollama_model",
                "faq_snapshot",
                "staff_addresses",
                "staff_domains",
                "ui_locale",
                "ui_theme",
                "gemini_reply_models",
                "openai_reply_models",
                "claude_reply_models",
                "ollama_reply_models",
                "gemini_embedding_models",
                "gemini_models_fetched_at",
                "provider_models_fetched_at",
            ]
            data = {k: get_setting(conn, k) for k in keys}
            qa_count = conn.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
            mail_count = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
            conv_count = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
            last_import = conn.execute(
                "SELECT completed_at FROM imports WHERE status='completed' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            gstats = graph_stats(conn)
            knowledge = knowledge_analysis(conn) if gstats.get("entity_count") else None
            auth = provider_auth_status(conn)
        provider = str(data.get("ai_provider") or "gemini").lower()
        catalog_key = {
            "gemini": "gemini_reply_models",
            "openai": "openai_reply_models",
            "claude": "claude_reply_models",
            "ollama": "ollama_reply_models",
        }.get(provider, "gemini_reply_models")
        reply_models = data.pop(catalog_key, None) or data.get("gemini_reply_models") or []
        for k in (
            "gemini_reply_models",
            "openai_reply_models",
            "claude_reply_models",
            "ollama_reply_models",
        ):
            data.pop(k, None)
        embedding_models = data.pop("gemini_embedding_models", None) or []
        models_fetched_at = data.pop("provider_models_fetched_at", None) or data.pop(
            "gemini_models_fetched_at", None
        )
        data.pop("gemini_models_fetched_at", None)
        if not isinstance(reply_models, list):
            reply_models = []
        if not isinstance(embedding_models, list):
            embedding_models = []
        data.update(
            {
                "has_api_key": bool(get_api_key()),
                "has_openai_api_key": bool(get_openai_api_key()),
                "has_claude_api_key": bool(get_claude_api_key()),
                "provider_auth": auth,
                "reply_models": reply_models,
                "embedding_models": embedding_models,
                "models_fetched_at": models_fetched_at,
                "stats": {
                    "messages": mail_count,
                    "conversations": conv_count,
                    "qa": qa_count,
                    "last_import_at": last_import["completed_at"] if last_import else None,
                },
                "graph": gstats,
                "knowledge": knowledge,
                "progress": STATE.progress,
            }
        )
        return {"success": True, "settings": data}

    if action == "save_settings":
        settings = payload.get("settings") or {}
        with STATE.conn() as conn:
            for key, value in settings.items():
                if key in SECRET_SETTING_KEYS:
                    continue
                set_setting(conn, key, value)
            log_event(conn, "info", "settings_updated", list(settings.keys()))
        return {"success": True}

    if action == "import_mail":
        import base64
        from datetime import datetime

        source_type = payload.get("source_type")
        path = payload.get("path")
        filename = payload.get("filename")
        content_base64 = payload.get("content_base64")

        if not source_type:
            return {"success": False, "error": "source_type is required"}

        path_obj: Path | None = None
        if content_base64 and filename:
            safe_name = Path(str(filename)).name
            if not safe_name:
                return {"success": False, "error": "filename is invalid"}
            imports_dir = STATE.workspace / "workspace" / "imports"
            imports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path_obj = imports_dir / f"{stamp}_{safe_name}"
            try:
                path_obj.write_bytes(base64.b64decode(content_base64))
            except Exception as exc:
                return {"success": False, "error": f"アップロードファイルの保存に失敗しました: {exc}"}
        elif path:
            path_obj = Path(path)
            if not path_obj.exists():
                return {"success": False, "error": f"file not found: {path}"}
        else:
            return {
                "success": False,
                "error": "ファイルを選択するか、path を指定してください",
            }

        def progress(stage: str, percent: float) -> None:
            STATE.progress = {"stage": stage, "percent": percent}

        with STATE.conn() as conn:
            staff_addresses = as_str_list(get_setting(conn, "staff_addresses", []))
            staff_domains = as_str_list(get_setting(conn, "staff_domains", []))
            result = run_import(
                conn,
                source_type=source_type,
                path=path_obj,
                staff_addresses=staff_addresses,
                staff_domains=staff_domains,
                progress=progress,
                lancedb_dir=STATE.lancedb_dir,
            )
            log_event(
                conn,
                "info",
                "import_completed",
                {**result, "saved_as": str(path_obj)},
            )
        STATE.progress = {"stage": "idle", "percent": 1.0}
        warnings = list(result.get("warnings") or [])
        embed_status = result.get("embed_status") or {}
        partial = bool(warnings) or bool(embed_status.get("error")) or (
            embed_status.get("skipped") == "no_api_key" and int(result.get("qa_count") or 0) > 0
        )
        return {
            "success": True,
            "partial": partial,
            "saved_as": str(path_obj),
            **result,
        }

    if action == "list_conversations":
        query = payload.get("query")
        with STATE.conn() as conn:
            return {
                "success": True,
                "conversations": conv_manager.list_conversations(conn, query=query),
            }

    if action == "list_imports":
        with STATE.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM imports ORDER BY id DESC LIMIT 50"
            ).fetchall()
            return {"success": True, "imports": [dict(r) for r in rows]}

    if action == "rebuild_rag":
        def progress(stage: str, percent: float) -> None:
            STATE.progress = {"stage": f"rag:{stage}", "percent": percent}

        with STATE.conn() as conn:
            result = rebuild_embeddings(
                conn, lancedb_dir=STATE.lancedb_dir, progress=progress
            )
            log_event(conn, "info", "rag_rebuild", result)
        STATE.progress = {"stage": "idle", "percent": 1.0}
        return result if "success" in result else {"success": True, **result}

    if action == "rebuild_graph":
        def progress(stage: str, percent: float) -> None:
            STATE.progress = {"stage": f"graph:{stage}", "percent": percent}

        full = bool(payload.get("full", True))
        with STATE.conn() as conn:
            result = rebuild_graph(
                conn, clear_existing=True, full=full, progress=progress
            )
            log_event(conn, "info", "graph_rebuild", result)
            stats = graph_stats(conn)
            trends = trend_analysis(conn)
            knowledge = knowledge_analysis(conn) if stats.get("entity_count") else None
        STATE.progress = {"stage": "idle", "percent": 1.0}
        return {
            "success": True,
            **result,
            "graph": stats,
            "trends": trends,
            "knowledge": knowledge,
        }

    if action == "reset_imported_data":
        confirm = str(payload.get("confirm") or "").strip().upper()
        if confirm not in {"RESET", "YES", "確認"}:
            return {
                "success": False,
                "error": "破壊的操作です。confirm=RESET を指定してください",
            }

        def progress(stage: str, percent: float) -> None:
            STATE.progress = {"stage": f"reset:{stage}", "percent": percent}

        include_conversations = payload.get("include_conversations")
        if include_conversations is None:
            include_conversations = True
        with STATE.conn() as conn:
            result = reset_imported_data(
                conn,
                lancedb_dir=STATE.lancedb_dir,
                include_conversations=bool(include_conversations),
                progress=progress,
            )
            log_event(conn, "warning", "imported_data_reset", result.get("before"))
            stats = {
                "messages": 0,
                "conversations": result.get("after", {}).get("conversations", 0),
                "qa": 0,
                "last_import_at": None,
            }
            gstats = graph_stats(conn)
        STATE.progress = {"stage": "idle", "percent": 1.0}
        return {
            "success": True,
            **result,
            "stats": stats,
            "graph": gstats,
            "trends": [],
            "knowledge": None,
        }

    if action == "graph_stats":
        with STATE.conn() as conn:
            return {
                "success": True,
                "graph": graph_stats(conn),
                "trends": trend_analysis(conn),
                "knowledge": knowledge_analysis(conn),
            }

    if action == "graph_search":
        query = (payload.get("query") or "").strip()
        mode = str(payload.get("mode") or "local").lower()
        if not query:
            return {"success": False, "error": "query is required"}
        with STATE.conn() as conn:
            if mode == "global":
                hits = global_search(conn, query)
            elif mode == "drift":
                hits = drift_search(conn, query)
            else:
                from graph import local_search

                hits = local_search(conn, query)
        return {"success": True, "mode": mode, "hits": hits}

    if action == "generate_faqs":
        limit = int(payload.get("limit") or 20)
        with STATE.conn() as conn:
            faqs = generate_faqs(conn, limit=limit)
            log_event(conn, "info", "faq_generated", {"count": len(faqs)})
        return {"success": True, "faqs": faqs}

    if action == "knowledge_analysis":
        with STATE.conn() as conn:
            return {"success": True, "knowledge": knowledge_analysis(conn)}

    if action == "export_workspace":
        result = export_workspace(STATE.workspace)
        with STATE.conn() as conn:
            log_event(conn, "info", "workspace_export", result.get("path"))
        return result

    if action == "import_workspace":
        path = payload.get("path")
        filename = payload.get("filename")
        content_base64 = payload.get("content_base64")
        path_obj = None
        if content_base64 and filename:
            import base64
            from datetime import datetime

            imports_dir = STATE.workspace / "workspace" / "imports"
            imports_dir.mkdir(parents=True, exist_ok=True)
            path_obj = imports_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{Path(str(filename)).name}"
            path_obj.write_bytes(base64.b64decode(content_base64))
        elif path:
            path_obj = Path(path)
        else:
            return {"success": False, "error": "workspace ZIP を指定してください"}
        result = import_workspace(path_obj, STATE.workspace)
        # reconnect db path after import
        STATE.db_path = sqlite_path(STATE.workspace)
        with STATE.conn() as conn:
            log_event(conn, "info", "workspace_import", result)
        return result

    if action == "set_openai_api_key":
        key = (payload.get("api_key") or "").strip()
        if not key:
            return {"success": False, "error": "api_key is required"}
        set_openai_api_key(key)
        return {"success": True}

    if action == "set_claude_api_key":
        key = (payload.get("api_key") or "").strip()
        if not key:
            return {"success": False, "error": "api_key is required"}
        set_claude_api_key(key)
        return {"success": True}

    if action == "refresh_provider_models":
        with STATE.conn() as conn:
            result = list_provider_models(conn)
            if result.get("success") and result.get("reply_models"):
                provider = str(get_setting(conn, "ai_provider", "gemini") or "gemini").lower()
                catalog_key = {
                    "gemini": "gemini_reply_models",
                    "openai": "openai_reply_models",
                    "claude": "claude_reply_models",
                    "ollama": "ollama_reply_models",
                }.get(provider, f"{provider}_reply_models")
                set_setting(conn, catalog_key, result["reply_models"])
                # Keep legacy key in sync only for Gemini so older UI paths keep working
                if provider == "gemini":
                    set_setting(conn, "gemini_reply_models", result["reply_models"])
                from datetime import datetime, timezone

                set_setting(
                    conn,
                    "provider_models_fetched_at",
                    datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                )
            return result

    if action == "get_conversation":
        conversation_id = int(payload["conversation_id"])
        with STATE.conn() as conn:
            return {"success": True, "conversation": conv_manager.get_conversation(conn, conversation_id)}

    if action == "update_conversation":
        conversation_id = int(payload["conversation_id"])
        with STATE.conn() as conn:
            if "title" in payload:
                conv_manager.update_title(conn, conversation_id, str(payload["title"]))
            if "status" in payload:
                conv_manager.set_status(conn, conversation_id, str(payload["status"]))
            return {"success": True, "conversation": conv_manager.get_conversation(conn, conversation_id)}

    if action == "generate_reply":
        content = (payload.get("content") or "").strip()
        if not content:
            return {"success": False, "error": "メール内容を入力してください"}
        conversation_id = payload.get("conversation_id")
        with STATE.conn() as conn:
            try:
                if conversation_id:
                    result = generate_for_existing(
                        conn, int(conversation_id), content, lancedb_dir=STATE.lancedb_dir
                    )
                else:
                    result = generate_for_new(conn, content, lancedb_dir=STATE.lancedb_dir)
                log_event(conn, "info", "generate_reply_ok", {"conversation_id": result["conversation"]["id"]})
                return result
            except Exception as exc:
                from ai.providers import classify_provider_error

                log_event(conn, "error", "generate_reply_failed", str(exc)[:200])
                mapped = classify_provider_error(exc)
                return {"success": False, **mapped}

    if action == "get_progress":
        return {"success": True, "progress": STATE.progress}

    return {"success": False, "error": f"unknown action: {action}"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep stdout clean for process managers; details go to app_logs.
        sys.stderr.write("sidecar: " + (fmt % args) + "\n")

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin") or ""
        # Local desktop / Vite only; avoid reflecting arbitrary Origins.
        if origin.startswith(("http://127.0.0.1", "http://localhost", "tauri://", "https://tauri.")):
            self.send_header("Access-Control-Allow-Origin", origin)
        elif not origin:
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _reject_non_local(self) -> bool:
        host = self.client_address[0]
        if host in {"127.0.0.1", "::1", "localhost"}:
            return False
        self._send(403, {"success": False, "error": "local connections only"})
        return True

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._reject_non_local():
            return
        self._send(200, {"success": True})

    def do_GET(self) -> None:  # noqa: N802
        if self._reject_non_local():
            return
        path = urlparse(self.path).path
        if path in {"/", "/health"}:
            self._send(200, handle_action({"action": "health"}))
            return
        self._send(404, {"success": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self._reject_non_local():
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            result = handle_action(payload)
            self._send(200, result)
        except Exception as exc:
            import os

            payload: dict[str, Any] = {"success": False, "error": str(exc)}
            if os.environ.get("MAILRAG_DEBUG") == "1":
                payload["trace"] = traceback.format_exc(limit=3)
            self._send(500, payload)


def main() -> None:
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    server = ThreadingHTTPServer((host, port), Handler)
    print(json.dumps({"event": "started", "host": host, "port": port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
