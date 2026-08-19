from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ssdv.accounting.equation import accounting_equation
from ssdv.cli import build_parser, main
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.ingest import IngestError, ingest_generic
from ssdv.mis import mis_snapshot
from ssdv.money import money
from ssdv.paths import repo_root
from ssdv.validate import INTEGRITY_GATES, run_gates

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def test_generic_ingest_posts_and_mis(session) -> None:
    result = ingest_generic(
        session,
        EXAMPLE / "journals.csv",
        EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
    )
    assert result.vouchers == 7
    assert result.first_date == date(2024, 4, 1)
    snap = accounting_equation(session, date(2024, 4, 30))
    assert snap.holds
    mis = mis_snapshot(session, date(2024, 4, 30))
    assert mis.company_name == "Sample Traders Pvt Ltd"
    assert mis.scenario_id == "imported"
    assert mis.fy.sales == money("150000")
    assert mis.series.categories == ("2024-04",)
    assert mis.series.sales == (money("150000"),)
    assert mis.series.purchases == (money("80000"),)
    assert mis.series.receipts == (money("118000"),)
    assert mis.series.payments == (money("94400"),)
    assert mis.series.opex == (money("20000"),)
    assert mis.working_capital == money("139000")
    assert mis.collection_efficiency == Decimal("0.7867")
    assert mis.ytd_profit == money("130000")
    assert mis.metrics.top_customer == "CUST-A"
    assert mis.metrics.top_customer_share >= 0.6
    gates = run_gates(session, date(2024, 4, 30))
    assert {g.name for g in gates} == INTEGRITY_GATES
    assert all(g.ok for g in gates)


def test_unmapped_ledger_is_rejected(session, tmp_path: Path) -> None:
    journals = tmp_path / "j.csv"
    journals.write_text(
        "voucher_id,date,account,debit,credit\n"
        "1,2024-04-01,Mystery ledger,100,0\n"
        "1,2024-04-01,310000,0,100\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestError, match="Unmapped ledger"):
        ingest_generic(session, journals)


def test_auto_mapping_heuristics_without_account_map(session, tmp_path: Path) -> None:
    journals = tmp_path / "j.csv"
    journals.write_text(
        "voucher_id,date,account,debit,credit\n"
        "1,2024-04-01,Sundry Debtors,100,0\n"
        "1,2024-04-01,Sales Account,0,100\n",
        encoding="utf-8",
    )
    result = ingest_generic(session, journals, company_name="Heuristic Co")
    assert result.vouchers == 1


def test_unbalanced_source_is_rejected(session, tmp_path: Path) -> None:
    journals = tmp_path / "j.csv"
    journals.write_text(
        "voucher_id,date,account,debit,credit\n"
        "1,2024-04-01,111000,100,0\n"
        "1,2024-04-01,310000,0,90\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestError, match="Unbalanced"):
        ingest_generic(session, journals)


def test_ingest_cli_writes_sidecar_db(tmp_path: Path) -> None:
    db = tmp_path / "imported.sqlite"
    code = main(
        [
            "--db",
            str(db),
            "ingest",
            "--source",
            "generic",
            "--journals",
            str(EXAMPLE / "journals.csv"),
            "--map",
            str(EXAMPLE / "ledger_map.csv"),
            "--name",
            "CLI Traders",
        ]
    )
    assert code == 0
    assert db.exists()
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        mis = mis_snapshot(session, date(2024, 4, 30))
        assert mis.company_name == "CLI Traders"
        assert mis.fy.sales == money("150000")


def test_ingest_parser_future_source() -> None:
    parser = build_parser()
    args = parser.parse_args(["ingest", "--source", "tally", "--journals", "x.csv"])
    assert args.source == "tally"
    assert main(["ingest", "--source", "tally", "--journals", "x.csv"]) == 1
