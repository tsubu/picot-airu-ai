"""Tests for v0.4 / Phase5 extensions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "python"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

from database.sqlite import connect, migrate  # noqa: E402
from graph import rebuild_graph  # noqa: E402
from graph.advanced import drift_search, generate_faqs, global_search, knowledge_analysis  # noqa: E402
from importer import IMPORTERS  # noqa: E402
from services.import_service import run_import  # noqa: E402

from fixtures import write_maildealer_sample  # noqa: E402
from workspace_io import export_workspace, import_workspace  # noqa: E402


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


def test_extended_importers_registered():
    for key in ("gmail_mbox", "outlook_csv", "zendesk_csv", "thunderbird", "eml"):
        assert key in IMPORTERS


def test_global_drift_faq_knowledge(db, sample_csv: Path):
    run_import(db, source_type="maildealer_csv", path=sample_csv)
    rebuild_graph(db)
    glob = global_search(db, "ABC-100 電源")
    drift = drift_search(db, "ABC-100 電源")
    faqs = generate_faqs(db, limit=5)
    knowledge = knowledge_analysis(db)
    assert isinstance(glob, list)
    assert isinstance(drift, list)
    assert faqs
    assert knowledge["qa_total"] >= 1
    assert "coverage_ratio" in knowledge


def test_workspace_export_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "MailRAG"
    monkeypatch.setenv("HOME", str(tmp_path))
    # force workspace under tmp by monkeypatching default root usage via explicit root
    from database.sqlite import migrate as _migrate
    from paths import ensure_workspace, sqlite_path

    sample_csv = write_maildealer_sample(tmp_path)
    ensure_workspace(root)
    db_path = sqlite_path(root)
    _migrate(db_path)
    conn = connect(db_path)
    run_import(conn, source_type="maildealer_csv", path=sample_csv)
    conn.close()

    exported = export_workspace(root)
    assert exported["success"] is True
    zip_path = Path(exported["path"])
    assert zip_path.exists()

    # mutate then import
    conn = connect(db_path)
    conn.execute("DELETE FROM qa_pairs")
    conn.commit()
    conn.close()

    result = import_workspace(zip_path, root)
    assert result["success"] is True
    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"] >= 1
    conn.close()
