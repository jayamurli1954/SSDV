from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from ssdv.cli import main
from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.forensics.gstr2b_recon import ReconSummary
from ssdv.officemitra.export import write_ppt
from ssdv.officemitra.quality import (
    GSTR2B_MAX_DEDUCTION,
    PPT_MIN_SCORE,
    ExportBlocked,
    assess_session,
    budget_sidecar_path,
    enrich_payload,
    gstr2b_signal,
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


def test_gstr2b_signal_off_plan_does_not_affect_score(tmp_path: Path) -> None:
    db = tmp_path / "ssdv_sample.sqlite"
    _load(db)
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        signal = gstr2b_signal(session, plan_id="starter")
    assert signal.checked is False
    assert signal.deduction == 0
    assert signal.reason == "not included in this plan"


def test_gstr2b_signal_no_purchase_bills_is_a_clean_noop(tmp_path: Path) -> None:
    # A day-book-only import (the current generic/tally connector path) has
    # no PurchaseBill rows yet — the signal must not fabricate a mismatch
    # against an empty table, even on a plan that includes the feature.
    db = tmp_path / "ssdv_sample.sqlite"
    _load(db)
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        signal = gstr2b_signal(session, plan_id="enterprise")
        report = assess_session(session, date(2024, 4, 30), db, fy_code=None)
    assert signal.checked is False
    assert "no structured purchase-bill detail" in signal.reason
    assert report.breakdown["gstr2b"]["checked"] is False
    assert report.breakdown["gstr2b"]["deduction"] == 0


def test_gstr2b_mismatch_deducts_score_proportionally(tmp_path: Path) -> None:
    # Once a vault does have purchase-bill detail and a GSTR-2B file, a real
    # ITC gap should shave points off the trust score, scaled by how big the
    # gap is relative to total portal ITC — not a flat pass/fail.
    db = tmp_path / "ssdv_sample.sqlite"
    _load(db)
    engine = make_engine(db)
    create_schema(engine)
    summary = ReconSummary(
        total_portal_itc=Decimal("10000"),
        total_books_itc=Decimal("5000"),
        itc_gap=Decimal("5000"),  # 50% of portal ITC unmatched in books
        rows=(),
    )
    fake_license = type("FakeLicense", (), {"plan_id": "enterprise"})()
    with session_scope(engine) as session, \
        patch("ssdv.officemitra.quality._row_count", return_value=1), \
        patch("ssdv.officemitra.quality.reconcile_2b", return_value=summary), \
        patch("ssdv.officemitra.quality.load_license", return_value=fake_license):
        signal = gstr2b_signal(session, plan_id="enterprise")
        report = assess_session(session, date(2024, 4, 30), db, fy_code=None)
    assert signal.checked is True
    assert signal.deduction == round(GSTR2B_MAX_DEDUCTION * 0.5)
    assert report.breakdown["gstr2b"]["itc_gap"] == "5000.00"
    assert report.score <= 100 - signal.deduction


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
