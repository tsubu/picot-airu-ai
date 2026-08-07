"""Core unit tests for Mail RAG Desktop Python engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "python"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

from ai.reply_generator import generate_reply  # noqa: E402
from database.models import MailMessage  # noqa: E402
from database.sqlite import connect, migrate  # noqa: E402
from importer.maildealer_csv import MailDealerCSVImporter  # noqa: E402
from mail.cleaner import clean_body  # noqa: E402
from mail.dedupe import body_hash  # noqa: E402
from mail.role_detector import RoleDetector, RoleDetectorConfig  # noqa: E402
from rag.hybrid_search import HybridSearch  # noqa: E402
from security.pii_masker import mask_pii  # noqa: E402
from services.import_service import run_import  # noqa: E402
from conversation.summary import build_extractive_summary  # noqa: E402

from fixtures import write_maildealer_sample  # noqa: E402


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    return write_maildealer_sample(tmp_path)


@pytest.fixture()
def db(tmp_path: Path):
    path = tmp_path / "test.sqlite3"
    migrate(path)
    conn = connect(path)
    yield conn
    conn.close()


def test_maildealer_csv_parser(sample_csv: Path):
    messages = MailDealerCSVImporter().import_file(sample_csv)
    assert len(messages) == 6
    assert messages[0].subject
    assert messages[0].source_type == "maildealer_csv"


def test_role_detector_staff_domain():
    detector = RoleDetector(RoleDetectorConfig(staff_domains={"example.com"}))
    staff = MailMessage(from_address="support@example.com", metadata={})
    customer = MailMessage(from_address="buyer@other.test", metadata={})
    assert detector.detect(staff) == "staff"
    assert detector.detect(customer) == "customer"


def test_role_hint():
    detector = RoleDetector()
    msg = MailMessage(from_address="x@y.z", metadata={"role_hint": "customer"})
    assert detector.detect(msg) == "customer"


def test_cleaner_strips_quote_and_html():
    text = "本文です\n> 引用行\n-- \n署名"
    assert "引用行" not in clean_body(text)
    assert "署名" not in clean_body(text)
    assert "hello" in clean_body(None, "<b>hello</b>")


def test_duplicate_body_hash_stable():
    msg = MailMessage(message_id="<a@b>", body_text="same", subject="s", from_address="a@b")
    assert body_hash(msg) == body_hash(msg)


def test_import_dedupe(db, sample_csv: Path, tmp_path: Path):
    first = run_import(db, source_type="maildealer_csv", path=sample_csv)
    second = run_import(db, source_type="maildealer_csv", path=sample_csv)
    assert first["new_messages"] == 6
    assert second["new_messages"] == 0
    assert second["duplicate_messages"] == 6
    qa = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    assert qa >= 2


def test_hybrid_search_keyword(db, sample_csv: Path):
    run_import(db, source_type="maildealer_csv", path=sample_csv)
    hits = HybridSearch(db, top_k=5).search("ABC-100 電源")
    assert hits
    assert any("ABC-100" in (h.get("question") or "") or "ABC-100" in (h.get("answer") or "") for h in hits)


def test_pii_mask():
    text = "連絡先は taro@example.com / 03-1234-5678 です"
    masked = mask_pii(text)
    assert "@" not in masked
    assert "03-1234-5678" not in masked
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked


def test_summary_extractive():
    messages = [
        {"role": "customer", "content": "電源が入らない"},
        {"role": "ai", "content": "アダプターを確認してください"},
    ]
    summary = build_extractive_summary(messages)
    assert "電源" in summary


def test_reply_insufficient_evidence():
    result = generate_reply(
        None,
        customer_message="未知の問い合わせ",
        conversation_summary=None,
        recent_messages=[],
        rag_hits=[],
        answer_style={},
        model=None,
        min_score=0.3,
    )
    assert result["insufficient_evidence"] is True
    assert "十分な過去対応" in result["answer"]


def test_ai_answer_not_written_to_qa(db, sample_csv: Path):
    """AI responses must not become QA knowledge automatically."""
    run_import(db, source_type="maildealer_csv", path=sample_csv)
    before = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    # Simulate storing AI reply only into conversation tables
    db.execute("INSERT INTO conversations(title, status) VALUES ('t', 'active')")
    cid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        "INSERT INTO conversation_messages(conversation_id, role, content) VALUES (?, 'ai', ?)",
        (cid, "これはAI返答案"),
    )
    db.commit()
    after = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    assert after == before
    assert db.execute(
        "SELECT COUNT(*) AS c FROM qa_pairs WHERE answer LIKE ?",
        ("%AI返答案%",),
    ).fetchone()["c"] == 0
