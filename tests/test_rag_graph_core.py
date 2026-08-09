"""Integration tests for Hybrid RAG + Graph RAG core paths."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "python"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

from database.sqlite import connect, migrate  # noqa: E402
from fixtures import write_maildealer_sample  # noqa: E402
from graph import extract_entities_from_qa, graph_stats, local_search, rebuild_graph  # noqa: E402
from graph.advanced import drift_search, generate_faqs, global_search, knowledge_analysis  # noqa: E402
from rag.hybrid_search import HybridSearch  # noqa: E402
from security.credentials import set_setting  # noqa: E402
from services.import_service import run_import  # noqa: E402
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


@pytest.fixture()
def imported(db, sample_csv: Path):
    result = run_import(db, source_type="maildealer_csv", path=sample_csv)
    assert result["new_messages"] == 6
    qa = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    assert qa >= 2
    return result


def test_hybrid_keyword_prefers_product_model(imported, db):
    hits = HybridSearch(db, top_k=5).search("ABC-100の電源が入らない")
    assert hits, "Hybrid keyword search returned no hits"
    blob = "\n".join(f"{h.get('question')}\n{h.get('answer')}" for h in hits)
    assert "ABC-100" in blob
    assert "電源" in blob or "点滅" in blob or "リセット" in blob
    assert float(hits[0].get("score") or 0) >= 0.25
    # Unrelated query should be weaker / empty compared to product query
    weak = HybridSearch(db, top_k=5).search("天気 予報 無関係")
    if weak:
        assert float(weak[0].get("score") or 0) < float(hits[0].get("score") or 0)


def test_hybrid_merge_rerank_boosts_dual_channel(imported, db):
    search = HybridSearch(db, top_k=5)
    kw = search.keyword_search("ABC-100 電源")
    assert kw
    qa_id = kw[0]["qa_id"]
    vectorish = [
        {
            "qa_id": qa_id,
            "question": kw[0]["question"],
            "answer": kw[0]["answer"],
            "score": 0.4,
            "source": "vector",
        }
    ]
    merged = search.merge_rerank(vectorish, kw)
    dual = next(h for h in merged if h["qa_id"] == qa_id)
    assert dual["source"] == "hybrid"
    assert float(dual["score"]) >= float(kw[0]["score"])


def test_graph_rebuild_links_product_problem_action(imported, db):
    result = rebuild_graph(db, clear_existing=True)
    assert result["entity_count"] > 0
    assert result["relation_count"] >= 0
    stats = graph_stats(db)
    assert stats["entity_count"] == result["entity_count"]
    assert (stats.get("by_type") or {}).get("product", 0) >= 1
    assert (stats.get("by_type") or {}).get("problem", 0) >= 1

    products = db.execute(
        "SELECT name FROM graph_entities WHERE entity_type='product'"
    ).fetchall()
    names = {r["name"] for r in products}
    assert "ABC-100" in names


def test_graph_local_global_drift_find_abc100(imported, db):
    rebuild_graph(db, clear_existing=True)
    query = "ABC-100 電源 点滅"

    local = local_search(db, query, limit=8)
    assert local, "Graph local_search returned empty"
    assert any(h.get("name") == "ABC-100" or "電源" in str(h.get("name")) for h in local)
    assert any(h.get("qa_ids") for h in local), "local hits should link back to QA ids"

    glob = global_search(db, query, limit=8)
    assert glob
    assert any(g.get("mode") == "global" for g in glob)

    drift = drift_search(db, query, limit=8)
    assert drift
    assert any(str(d.get("mode", "")).startswith("drift") for d in drift)


def test_graph_enrichment_adds_linked_qa_into_hits(imported, db, tmp_path: Path, monkeypatch):
    rebuild_graph(db, clear_existing=True)
    set_setting(db, "use_graph_rag", True)
    set_setting(db, "graph_search_mode", "local")
    set_setting(db, "rag_min_score", 0.1)
    set_setting(db, "allow_offline_draft", True)
    monkeypatch.setattr("services.reply_service.build_ai_provider", lambda _conn: None)

    result = generate_for_new(
        db,
        "ABC-100の電源が入らず赤いランプが点滅します",
        lancedb_dir=tmp_path / "lance",
    )
    assert result["success"] is True
    assert isinstance(result.get("graph_hits"), list)
    assert result["graph_hits"], "expected Graph local hits for ABC-100 power issue"
    # Offline provider should still produce a draft when Hybrid finds evidence
    assert result.get("insufficient_evidence") is False
    assert result.get("answer")
    assert result.get("sources")


def test_reply_modes_local_global_drift(imported, db, tmp_path: Path, monkeypatch):
    rebuild_graph(db, clear_existing=True)
    monkeypatch.setattr("services.reply_service.build_ai_provider", lambda _conn: None)
    set_setting(db, "use_graph_rag", True)
    set_setting(db, "rag_min_score", 0.1)
    set_setting(db, "allow_offline_draft", True)

    for mode in ("local", "global", "drift"):
        set_setting(db, "graph_search_mode", mode)
        result = generate_for_new(
            db,
            "ABC-100の電源が入らない",
            lancedb_dir=tmp_path / f"lance-{mode}",
        )
        assert result["success"] is True
        assert result.get("graph_hits") is not None
        assert len(result["graph_hits"]) >= 1, f"mode={mode} produced no graph hits"


def test_reply_without_graph_still_works(imported, db, tmp_path: Path, monkeypatch):
    set_setting(db, "use_graph_rag", False)
    set_setting(db, "rag_min_score", 0.1)
    set_setting(db, "allow_offline_draft", True)
    monkeypatch.setattr("services.reply_service.build_ai_provider", lambda _conn: None)
    result = generate_for_new(
        db,
        "ABC-100の電源が入らない",
        lancedb_dir=tmp_path / "lance-nograph",
    )
    assert result["success"] is True
    assert result.get("graph_hits") == [] or result.get("graph_hits") is not None
    assert result.get("insufficient_evidence") is False
    assert result.get("sources")


def test_ai_reply_never_increases_qa_knowledge(imported, db, tmp_path: Path, monkeypatch):
    rebuild_graph(db, clear_existing=True)
    before = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    monkeypatch.setattr("services.reply_service.build_ai_provider", lambda _conn: None)
    set_setting(db, "use_graph_rag", True)
    set_setting(db, "rag_min_score", 0.1)
    set_setting(db, "allow_offline_draft", True)
    generate_for_new(
        db,
        "ABC-100の電源が入らない点滅",
        lancedb_dir=tmp_path / "lance-qa-guard",
    )
    after = db.execute("SELECT COUNT(*) AS c FROM qa_pairs").fetchone()["c"]
    assert after == before


def test_faq_and_knowledge_analysis(imported, db):
    rebuild_graph(db, clear_existing=True)
    faqs = generate_faqs(db, limit=5)
    assert faqs
    knowledge = knowledge_analysis(db)
    assert knowledge["qa_total"] >= 2
    assert knowledge["coverage_ratio"] >= 0
    assert "qa_without_graph_link" in knowledge


def test_entity_extraction_core_fields():
    data = extract_entities_from_qa(
        "ABC-100の電源が入らない。赤いランプが点滅します。",
        "ACアダプターを確認し、本体リセットを実施してください。",
    )
    assert "ABC-100" in data["product"]
    assert any("電源" in p or "点滅" in p for p in data["problem"])
    assert any("アダプター" in c for c in data["cause"])
    assert any("リセット" in a for a in data["action"])
