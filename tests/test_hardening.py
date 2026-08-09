"""Tests for PII masking, vector embedding path, Outlook/Zendesk importers."""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "python"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

from database.sqlite import connect, migrate  # noqa: E402
from fixtures import write_maildealer_sample  # noqa: E402
from importer.extended import OutlookCsvImporter, ZendeskCsvImporter  # noqa: E402
from rag.embedding_store import upsert_qa_embeddings  # noqa: E402
from rag.hybrid_search import HybridSearch  # noqa: E402
from rag.incremental import embed_new_qa_pairs  # noqa: E402
from security.pii_masker import PiiMaskConfig, mask_pii  # noqa: E402
from services.import_service import run_import  # noqa: E402
from services.reply_service import generate_for_new  # noqa: E402


@pytest.fixture()
def db(tmp_path: Path):
    path = tmp_path / "test.sqlite3"
    migrate(path)
    conn = connect(path)
    yield conn
    conn.close()


class FakeEmbedder:
    """Deterministic bag-of-tokens embedding for offline LanceDB tests."""

    dim = 32

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            tokens = set()
            lowered = text.lower()
            for i in range(len(lowered) - 1):
                tokens.add(lowered[i : i + 2])
            for tok in tokens:
                digest = hashlib.sha256(tok.encode("utf-8")).digest()
                idx = digest[0] % self.dim
                vec[idx] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


def test_pii_masks_address_and_name():
    text = (
        "連絡先は taro@example.com / 03-1234-5678 です。"
        "住所は〒100-0001 東京都千代田区千代田1-1-1です。"
        "氏名: 山田太郎 様、注文番号 ORD-12345。"
    )
    masked = mask_pii(
        text,
        PiiMaskConfig(
            mask_email=True,
            mask_phone=True,
            mask_address=True,
            mask_name=True,
            mask_order_id=True,
        ),
    )
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked
    assert "[ADDRESS]" in masked
    assert "東京都千代田区" not in masked
    assert "[NAME]" in masked
    assert "山田太郎" not in masked
    assert "[ORDER]" in masked


def test_pii_name_patterns_and_honorific():
    masked = mask_pii(
        "佐藤花子さんへご連絡ください。",
        PiiMaskConfig(mask_name=True, name_patterns=["特別顧客"]),
    )
    assert "[NAME]" in masked
    assert "佐藤花子" not in masked


def test_outlook_csv_realish_headers(tmp_path: Path):
    path = tmp_path / "outlook.csv"
    path.write_text(
        "\n".join(
            [
                "Subject,Body,From: (Name),From: (Address),To: (Name),To: (Address),Sent",
                (
                    "ABC-100 power,"
                    '"Power will not turn on",'
                    "Customer A,"
                    "customer@example.com,"
                    "Support,"
                    "support@example.com,"
                    "2026-07-01 10:00:00"
                ),
                (
                    "Re: ABC-100 power,"
                    '"Please check the AC adapter",'
                    "Support,"
                    "support@example.com,"
                    "Customer A,"
                    "customer@example.com,"
                    "2026-07-01 10:15:00"
                ),
            ]
        ),
        encoding="utf-8",
    )
    messages = OutlookCsvImporter().import_file(path)
    assert len(messages) == 2
    assert messages[0].source_type == "outlook_csv"
    assert messages[0].from_address == "customer@example.com"
    assert messages[0].to_addresses == ["support@example.com"]
    assert messages[0].metadata.get("role_hint") == "customer"
    assert "Power will not turn on" in messages[0].body_text
    assert messages[1].from_address == "support@example.com"
    assert messages[1].metadata.get("role_hint") == "staff"


def test_zendesk_csv_comment_rows(tmp_path: Path):
    path = tmp_path / "zendesk.csv"
    path.write_text(
        "\n".join(
            [
                "Ticket ID,Subject,Requester,Assignee,Created at,Comment,Comment Author",
                (
                    "1001,Return request,customer@example.com,agent@example.com,"
                    "2026-07-02 09:00:00,I want to return XYZ-200,customer@example.com"
                ),
                (
                    "1001,Return request,customer@example.com,agent@example.com,"
                    "2026-07-02 09:30:00,Please use the return form,agent@example.com"
                ),
            ]
        ),
        encoding="utf-8",
    )
    messages = ZendeskCsvImporter().import_file(path)
    assert len(messages) == 2
    assert messages[0].source_type == "zendesk_csv"
    assert messages[0].metadata.get("ticket_id") == "1001"
    assert messages[0].metadata.get("role_hint") == "customer"
    assert messages[1].metadata.get("role_hint") == "staff"
    assert "XYZ-200" in messages[0].body_text


def test_vector_embedding_and_hybrid_merge(db, tmp_path: Path):
    sample = write_maildealer_sample(tmp_path)
    run_import(
        db,
        source_type="maildealer_csv",
        path=sample,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    lance = tmp_path / "lancedb"
    embedder = FakeEmbedder()
    result = embed_new_qa_pairs(db, lancedb_dir=lance, embedder=embedder)
    assert result["embedded"] >= 2

    # status rows marked
    marked = db.execute("SELECT COUNT(*) AS c FROM qa_embedding_status").fetchone()["c"]
    assert marked >= 2

    query = "ABC-100 電源 点滅"
    qvec = embedder.embed([query])[0]
    hits = HybridSearch(db, lancedb_dir=lance, top_k=5).search(query, query_vector=qvec)
    assert hits
    assert any(h.get("source") in {"vector", "hybrid", "keyword"} for h in hits)
    blob = "\n".join(f"{h.get('question')}\n{h.get('answer')}" for h in hits)
    assert "ABC-100" in blob or "電源" in blob or "点滅" in blob


def test_reply_uses_vector_when_embedder_available(db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sample = write_maildealer_sample(tmp_path)
    run_import(
        db,
        source_type="maildealer_csv",
        path=sample,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    lance = tmp_path / "lancedb"
    embedder = FakeEmbedder()
    embed_new_qa_pairs(db, lancedb_dir=lance, embedder=embedder)

    monkeypatch.setattr("services.reply_service.build_ai_provider", lambda _conn: None)
    monkeypatch.setattr("services.reply_service.build_embedding_provider", lambda _conn: embedder)

    from security.credentials import set_setting

    set_setting(db, "rag_min_score", 0.05)
    set_setting(db, "use_graph_rag", False)
    set_setting(db, "allow_offline_draft", True)
    out = generate_for_new(db, "ABC-100の電源が入らない", lancedb_dir=lance)
    assert out["success"] is True
    assert out.get("insufficient_evidence") is False
    assert out.get("sources")


def test_offline_draft_requires_opt_in(db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sample = write_maildealer_sample(tmp_path)
    run_import(
        db,
        source_type="maildealer_csv",
        path=sample,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    from security.credentials import set_setting

    set_setting(db, "rag_min_score", 0.05)
    set_setting(db, "use_graph_rag", False)
    set_setting(db, "allow_offline_draft", False)
    monkeypatch.setattr("services.reply_service.build_ai_provider", lambda _conn: None)
    monkeypatch.setattr("services.reply_service.build_embedding_provider", lambda _conn: None)
    out = generate_for_new(db, "ABC-100の電源が入らない", lancedb_dir=tmp_path / "lancedb")
    assert out["success"] is False
    assert out.get("error_code") == "missing_api_key"
    assert "API" in (out.get("error") or "") or "オフライン" in (out.get("error") or "")


def test_classify_provider_error_codes():
    from ai.providers import classify_provider_error, provider_auth_status
    from database.sqlite import connect, migrate
    from pathlib import Path
    import tempfile

    mapped = classify_provider_error(RuntimeError("401 Unauthorized invalid api key"))
    assert mapped["error_code"] == "invalid_api_key"
    mapped = classify_provider_error(RuntimeError("429 quota exceeded"))
    assert mapped["error_code"] == "api_quota"
    mapped = classify_provider_error(RuntimeError("connection timed out"))
    assert mapped["error_code"] == "api_unreachable"

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "t.sqlite3"
        migrate(path)
        conn = connect(path)
        from security.credentials import set_setting

        set_setting(conn, "ai_provider", "openai")
        status = provider_auth_status(conn)
        # OpenAI key is not set in isolated test keyring account for this process
        # (may still exist globally — assert shape instead of absolute ready=False)
        assert status["provider"] == "openai"
        assert status["requires_api_key"] is True
        assert status["code"] in {"ok", "missing_api_key"}
        if status["ready"] is False:
            assert "API" in (status.get("message") or "")
        conn.close()


def test_as_bool_coercion():
    from security.credentials import as_bool

    assert as_bool(True) is True
    assert as_bool(False) is False
    assert as_bool("false") is False
    assert as_bool("true") is True
    assert as_bool("0") is False
    assert as_bool(None, True) is True


def test_rebuild_does_not_mark_failed_batches(db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db.execute(
        "INSERT INTO qa_pairs(question, answer, confidence, verified, created_at) VALUES (?, ?, 0.5, 0, datetime('now'))",
        ("q", "a"),
    )
    db.commit()

    class BadEmbedder:
        def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
            raise RuntimeError("embed failed")

    monkeypatch.setattr("rag.incremental.build_embedding_provider", lambda _conn: BadEmbedder())
    from rag.rebuild import rebuild_embeddings

    result = rebuild_embeddings(db, lancedb_dir=tmp_path / "lance")
    assert result["success"] is False
    pending = db.execute("SELECT COUNT(*) AS c FROM qa_embedding_status").fetchone()["c"]
    assert pending == 0


def test_reply_masks_all_prompt_fields(monkeypatch: pytest.MonkeyPatch):
    from ai.reply_generator import generate_reply
    from security.pii_masker import PiiMaskConfig

    captured: dict[str, str] = {}

    class CapturingProvider:
        def generate(self, prompt: str, *, model: str | None = None) -> str:
            captured["prompt"] = prompt
            return "返信案です"

    generate_reply(
        CapturingProvider(),
        customer_message="顧客は taro@example.com です",
        conversation_summary="前回連絡先は hana@example.com",
        recent_messages=[{"role": "customer", "content": "電話 03-1111-2222"}],
        rag_hits=[
            {
                "qa_id": 1,
                "question": "連絡先は old@example.com?",
                "answer": "support@example.com へ",
                "score": 0.9,
            }
        ],
        answer_style={},
        model="x",
        min_score=0.1,
        pii_config=PiiMaskConfig(mask_email=True, mask_phone=True),
        graph_context=[{"entity_type": "person", "name": "secret@example.com", "score": 0.5, "neighbors": []}],
    )
    prompt = captured["prompt"]
    assert "taro@example.com" not in prompt
    assert "hana@example.com" not in prompt
    assert "03-1111-2222" not in prompt
    assert "old@example.com" not in prompt
    assert "secret@example.com" not in prompt
    assert "[EMAIL]" in prompt
    assert "[PHONE]" in prompt


def test_upsert_qa_embeddings_roundtrip(tmp_path: Path):
    lance = tmp_path / "lancedb"
    rows = [
        {"qa_id": 1, "question": "q1", "answer": "a1", "vector": [0.1, 0.2, 0.3]},
        {"qa_id": 2, "question": "q2", "answer": "a2", "vector": [0.3, 0.2, 0.1]},
    ]
    assert upsert_qa_embeddings(lance, rows) == 2
    # update existing
    rows[0]["vector"] = [0.9, 0.1, 0.0]
    assert upsert_qa_embeddings(lance, rows[:1]) == 1


def test_secret_keys_rejected_from_sqlite(db):
    from security.credentials import SECRET_SETTING_KEYS, set_setting

    for key in SECRET_SETTING_KEYS:
        with pytest.raises(ValueError):
            set_setting(db, key, "sk-secret")


def test_graph_qa_alone_is_not_evidence():
    from ai.reply_generator import generate_reply

    result = generate_reply(
        None,
        customer_message="未知",
        conversation_summary=None,
        recent_messages=[],
        rag_hits=[
            {
                "qa_id": 9,
                "question": "graph only",
                "answer": "should not draft",
                "score": 0.55,
                "source": "graph-qa",
                "evidence": False,
            }
        ],
        answer_style={},
        model=None,
        min_score=0.1,
        allow_offline_draft=True,
    )
    assert result["insufficient_evidence"] is True


def test_as_str_list_normalizes_staff_settings():
    from security.credentials import as_str_list

    assert as_str_list("support@example.com, help@example.com") == [
        "support@example.com",
        "help@example.com",
    ]
    assert as_str_list(["a@b.com", " ", "c@d.com"]) == ["a@b.com", "c@d.com"]
    assert as_str_list(None) == []


def test_zip_slip_rejected(tmp_path: Path):
    from workspace_io import import_workspace

    evil = tmp_path / "evil.zip"
    with __import__("zipfile").ZipFile(evil, "w") as zf:
        zf.writestr("../escape.txt", "nope")
    result = import_workspace(evil, root=tmp_path / "ws")
    assert result["success"] is False
    assert "ZIP" in (result.get("error") or "") or "unsafe" in (result.get("error") or "")


def test_reset_imported_data_clears_knowledge(db, tmp_path: Path):
    from graph import rebuild_graph
    from security.credentials import set_setting
    from services.data_reset import reset_imported_data

    sample = write_maildealer_sample(tmp_path)
    run_import(
        db,
        source_type="maildealer_csv",
        path=sample,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    rebuild_graph(db, clear_existing=True, full=True)
    set_setting(db, "faq_snapshot", [{"question": "q", "answer": "a"}])
    set_setting(db, "company_name", "PICOT")
    lance = tmp_path / "lancedb"
    lance.mkdir()
    (lance / "dummy.txt").write_text("x", encoding="utf-8")

    assert db.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"] > 0
    assert db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"] > 0
    assert db.execute("SELECT COUNT(*) AS c FROM graph_entities").fetchone()["c"] > 0

    result = reset_imported_data(db, lancedb_dir=lance, include_conversations=True)
    assert result["success"] is True
    assert db.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM graph_entities").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM imports").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"] == 0
    # settings preserved
    from security.credentials import get_setting

    assert get_setting(db, "company_name") == "PICOT"
    assert get_setting(db, "faq_snapshot") == []


def test_graph_full_rebuild_purges_history(db, tmp_path: Path):
    from graph import rebuild_graph

    sample = write_maildealer_sample(tmp_path)
    run_import(
        db,
        source_type="maildealer_csv",
        path=sample,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    first = rebuild_graph(db, clear_existing=True, full=False)
    assert first["entity_count"] > 0
    builds_before = db.execute("SELECT COUNT(*) AS c FROM graph_builds").fetchone()["c"]
    assert builds_before >= 1

    second = rebuild_graph(db, full=True)
    assert second["full"] is True
    assert second["entity_count"] > 0
    # full purge removes old builds then inserts one new row
    builds_after = db.execute("SELECT COUNT(*) AS c FROM graph_builds").fetchone()["c"]
    assert builds_after == 1
    detail = db.execute("SELECT detail FROM graph_builds ORDER BY id DESC LIMIT 1").fetchone()["detail"]
    assert detail == "full"


def test_duplicate_customer_still_pairs_new_staff(db, tmp_path: Path):
    sample = write_maildealer_sample(tmp_path)
    first = run_import(
        db,
        source_type="maildealer_csv",
        path=sample,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    assert first["qa_count"] >= 1
    before = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]

    # Second import: all messages duplicate, but if we append a new staff reply CSV it should pair.
    # Simulate: re-import same file (dups) then manually ensure pending path works via sorted stream.
    second = run_import(
        db,
        source_type="maildealer_csv",
        path=sample,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    assert second["duplicate_messages"] >= 1
    after = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    assert after == before  # pure re-import must not duplicate QA

    # New staff-only follow-up after duplicate customer context
    follow = tmp_path / "follow.csv"
    follow.write_text(
        "\n".join(
            [
                "mail_id,message_id,subject,from,to,date,body,role",
                (
                    'MD-1001,<md1001@example.com>,ABC-100の電源について,'
                    'customer1@example.com,support@example.com,2026-07-01 10:00:00,'
                    '"ABC-100の電源が入りません。どうすればよいでしょうか？",customer'
                ),
                (
                    'MD-1009,<md1009@example.com>,Re: ABC-100の電源について,'
                    'support@example.com,customer1@example.com,2026-07-01 12:00:00,'
                    '"追加でファームウェア更新もご確認ください。",staff'
                ),
            ]
        ),
        encoding="utf-8",
    )
    # First customer row duplicates; staff is new → QA should still form via pending restore
    third = run_import(
        db,
        source_type="maildealer_csv",
        path=follow,
        staff_addresses=["support@example.com"],
        staff_domains=["example.com"],
    )
    assert third["duplicate_messages"] >= 1
    assert third["qa_count"] >= 1
    assert db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"] > before

