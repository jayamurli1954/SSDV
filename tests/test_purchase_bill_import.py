"""Purchase register import enables GSTR-2B recon on day-book-only vaults."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.forensics.gstr2b_recon import load_gstr2b_csv, reconcile_2b
from ssdv.ingest.purchase_bills import load_purchase_bills_csv
from ssdv.models import PurchaseBill
from ssdv.officemitra.quality import gstr2b_signal
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"
RECON = repo_root() / "examples" / "gstr2b_recon"


def test_purchase_register_import_then_gstr2b_quality_gate(tmp_path: Path) -> None:
    db = tmp_path / "client.sqlite"
    load_into_vault(
        db,
        source="generic",
        journals=EXAMPLE / "journals.csv",
        account_map=EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
        force=True,
    )
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        before = int(session.scalar(select(func.count()).select_from(PurchaseBill)) or 0)
        assert before == 0
        silent = gstr2b_signal(session, plan_id="enterprise")
        assert silent.checked is False
        assert "no structured purchase-bill detail" in (silent.reason or "")

        imported = load_purchase_bills_csv(session, RECON / "purchase_register.csv")
        assert imported.bills == 3
        assert imported.vendors_created >= 1

        load_gstr2b_csv(session, RECON / "gstr2b_sample.csv")
        summary = reconcile_2b(session, "2024-04")
        flags = {r.flag for r in summary.rows}
        assert "missing_in_books" in flags  # PORTAL-ONLY-1

        signal = gstr2b_signal(session, plan_id="enterprise", return_period="2024-04")
        assert signal.checked is True
        assert signal.deduction >= 0
        report_reason = signal.reason
        assert report_reason is None


def test_purchase_register_does_not_require_synthetic_init(tmp_path: Path) -> None:
    db = tmp_path / "bare.sqlite"
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        result = load_purchase_bills_csv(session, RECON / "purchase_register.csv")
        assert result.bills == 3
        n = session.scalar(select(func.count()).select_from(PurchaseBill))
        assert int(n or 0) == 3
