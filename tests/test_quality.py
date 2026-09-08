from datetime import date
from pathlib import Path

import pytest

from ssdv.cli import main
from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.officemitra.export import write_ppt
from ssdv.officemitra.quality import (
    PPT_MIN_SCORE,
    ExportBlocked,
    assess_session,
    budget_sidecar_path,
    enrich_payload,
    mark_reviewed,
    score_from_gates,
)
from ssdv.paths import repo_root
from ssdv.validate import Gate

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def _load(db: Path) -> None:
    load_into_vault(
        db,
        source="generic",
        journals=EXAMPLE / "journals.csv",
        account_map=EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
        force=True,
    )


def test_score_from_gates_integrity_failure_is_low() -> None:
    gates = [
        Gate("trial_balance", False, "off"),
        Gate("accounting_equation", True, "ok"),
    ]
    score, breakdown = score_from_gates(gates, imported=True, has_budget=True)
    assert score < PPT_MIN_SCORE
    assert breakdown["integrity_ok"] is False


def test_imported_vault_without_budget_is_medium(tmp_path: Path) -> None:
    db = tmp_path / "ssdv_sample.sqlite"
    _load(db)
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        report = assess_session(session, date(2024, 4, 30), db)
    assert report.imported is True
    assert report.has_budget is False
    assert report.band in {"medium", "high"}
    assert report.score >= PPT_MIN_SCORE
    assert report.reviewed is False
    assert report.ppt_allowed is False


def test_write_ppt_blocked_without_review(tmp_path: Path) -> None:
    with pytest.raises(ExportBlocked):
        write_ppt({"ppt_allowed": False, "ppt_block_reason": "not reviewed"}, tmp_path / "x.pptx")


def test_budget_sidecar_and_review_unlock_ppt(tmp_path: Path) -> None:
    pytest.importorskip("pptx")
    db = tmp_path / "ssdv_sample.sqlite"
    _load(db)
    budget_sidecar_path(db).write_text("sales: 180000\n", encoding="utf-8")
    engine = make_engine(db)
    create_schema(engine)
    as_of = date(2024, 4, 30)
    with session_scope(engine) as session:
        before = assess_session(session, as_of, db)
        assert before.has_budget is True
        assert before.sales_budget is not None
        assert before.ppt_allowed is False
        mark_reviewed(db, as_of, session=session)
        after = assess_session(session, as_of, db)
        payload = enrich_payload({"kpis": {"sales": "150000", "plan": "0"}, "fy": {}}, session, db, as_of)
    assert after.reviewed is True
    assert after.ppt_allowed is True
    assert payload["data_quality_score"] == after.score
    assert payload["budget_vs_actual"]["sales_budget"] == "180000.00"
    assert payload["budget_vs_actual"]["variance_abs"] == "-30000.00"
    write_ppt(payload, tmp_path / "board.pptx")
    assert (tmp_path / "board.pptx").is_file()


def test_review_cli_then_ppt(tmp_path: Path) -> None:
    pytest.importorskip("pptx")
    pytest.importorskip("openpyxl")
    db = tmp_path / "connected.sqlite"
    _load(db)
    budget_sidecar_path(db).write_text("sales: 150000\n", encoding="utf-8")
    assert main(["--db", str(db), "review", "--as-of", "2024-04-30"]) == 0
    out = tmp_path / "mis.html"
    code = main(
        [
            "--db",
            str(db),
            "dashboard",
            "--as-of",
            "2024-04-30",
            "--out",
            str(out),
            "--ppt",
            "--excel",
        ]
    )
    assert code == 0
    assert out.with_suffix(".pptx").is_file()
    assert out.with_suffix(".xlsx").is_file()
