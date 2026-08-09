"""Tests for v0.2/v0.3 graph and importer extensions."""

from __future__ import annotations

import email
import mailbox
import sys
from email.message import EmailMessage
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "python"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

from database.sqlite import connect, migrate  # noqa: E402
from graph import extract_entities_from_qa, local_search, rebuild_graph  # noqa: E402
from importer.eml import EmlImporter  # noqa: E402
from importer.thunderbird import ThunderbirdImporter  # noqa: E402
from services.import_service import run_import  # noqa: E402

from fixtures import write_maildealer_sample  # noqa: E402
from services.reply_service import generate_for_new  # noqa: E402


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


def test_entity_extraction():
    data = extract_entities_from_qa(
        "ABC-100の電源が入らない",
        "ACアダプターを確認し、リセットしてください。",
    )
    assert "ABC-100" in data["product"]
    assert "電源が入らない" in data["problem"]
    assert "アダプター" in data["cause"]
    assert "リセット" in data["action"]


def test_graph_rebuild_and_local_search(db, sample_csv: Path):
    run_import(db, source_type="maildealer_csv", path=sample_csv)
    result = rebuild_graph(db)
    assert result["entity_count"] > 0
    assert result["relation_count"] >= 0
    hits = local_search(db, "ABC-100 電源")
    assert hits
    assert any(h["name"] == "ABC-100" or "電源" in h["name"] for h in hits)


def test_hybrid_works_without_graph(db, sample_csv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_import(db, source_type="maildealer_csv", path=sample_csv)
    from security.credentials import set_setting

    set_setting(db, "allow_offline_draft", True)
    monkeypatch.setattr("services.reply_service.build_ai_provider", lambda _conn: None)
    # no graph rebuild
    result = generate_for_new(
        db,
        "ABC-100の電源が入らずランプが点滅します",
        lancedb_dir=tmp_path / "lancedb",
    )
    assert result["success"] is True
    assert isinstance(result.get("graph_hits"), list)


def test_thunderbird_and_eml_importers(tmp_path: Path):
    mbox_path = tmp_path / "tb.mbox"
    mbox = mailbox.mbox(str(mbox_path))
    msg = EmailMessage()
    msg["From"] = "customer@other.test"
    msg["To"] = "support@example.com"
    msg["Subject"] = "Hello"
    msg["Message-ID"] = "<tb1@example.com>"
    msg.set_content("テスト本文")
    mbox.add(msg)
    mbox.close()

    tb = ThunderbirdImporter().import_file(mbox_path)
    assert len(tb) == 1
    assert tb[0].source_type == "thunderbird"

    eml_path = tmp_path / "one.eml"
    raw = email.message_from_string(msg.as_string())
    eml_path.write_bytes(raw.as_bytes())
    emls = EmlImporter().import_file(eml_path)
    assert len(emls) == 1
    assert emls[0].source_type == "eml"
