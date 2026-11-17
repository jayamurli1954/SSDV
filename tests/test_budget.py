from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.money import ZERO, money
from ssdv.officemitra.budget import (
    AccountActual,
    AccountBudget,
    build_variance,
    elapsed_fraction,
    load_account_budget,
)
from ssdv.officemitra.export import write_excel
from ssdv.officemitra.quality import budget_sidecar_path, enrich_payload
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"
AS_OF = date(2024, 4, 30)

CHART = [
    AccountActual("410000", "Sales", "income", ZERO),
    AccountActual("610000", "Salaries", "expense", ZERO),
    AccountActual("620000", "Rent", "expense", ZERO),
    AccountActual("627000", "Professional Fees", "expense", ZERO),
]


def _actual(code: str, amount: str) -> AccountActual:
    account = next(item for item in CHART if item.code == code)
    return AccountActual(code, account.name, account.type, money(amount))


def test_elapsed_fraction_of_financial_year() -> None:
    assert elapsed_fraction(date(2024, 4, 30)) == Decimal(30) / Decimal(365)
    assert elapsed_fraction(date(2025, 3, 31)) == Decimal(1)


def test_variance_signs_and_driver_ranking() -> None:
    report = build_variance(
        budget=AccountBudget(
            basis="to_date",
            amounts={
                "410000": money("200000"),
                "rent": money("15000"),
                "610000": money("50000"),
                "Marketing": money("9000"),
            },
        ),
        actuals=[
            _actual("410000", "150000"),
            _actual("620000", "20000"),
            _actual("610000", "40000"),
            _actual("627000", "7000"),
        ],
        chart=CHART,
        as_of=AS_OF,
    )
    rows = {row.code: row for row in report.rows}
    # Income below budget hurts profit; expense above budget hurts profit.
    assert rows["410000"].variance == money("-50000")
    assert rows["410000"].profit_impact == money("-50000")
    assert rows["410000"].favourable is False
    assert rows["410000"].variance_pct == Decimal("-0.2500")
    assert rows["620000"].variance == money("5000")
    assert rows["620000"].profit_impact == money("-5000")
    # Expense below budget helps profit.
    assert rows["610000"].profit_impact == money("10000")
    assert rows["610000"].favourable is True
    assert [row.code for row in report.drivers] == ["410000", "610000", "620000"]
    assert report.profit_impact == money("-45000")
    assert report.unmatched == ("Marketing",)
    assert report.unbudgeted_count == 1
    assert report.unbudgeted_expense == money("7000")


def test_annual_budget_is_pro_rated_and_missing_actual_is_zero() -> None:
    report = build_variance(
        budget=AccountBudget(
            basis="annual", amounts={"410000": money("2190000"), "610000": money("365000")}
        ),
        actuals=[_actual("410000", "150000")],
        chart=CHART,
        as_of=AS_OF,
    )
    rows = {row.code: row for row in report.rows}
    assert rows["410000"].budget == money("180000")
    assert rows["410000"].variance == money("-30000")
    assert rows["610000"].budget == money("30000")
    assert rows["610000"].actual == ZERO
    assert rows["610000"].profit_impact == money("30000")


def test_sidecar_loader_handles_flat_fy_and_bad_basis(tmp_path: Path) -> None:
    db = tmp_path / "ssdv_client.sqlite"
    sidecar = budget_sidecar_path(db)
    assert load_account_budget(db, fy="FY2024-25") is None

    sidecar.write_text("sales: 180000\n", encoding="utf-8")
    assert load_account_budget(db, fy="FY2024-25") is None

    sidecar.write_text("accounts:\n  410000: 2190000\n  Rent: 182500\n", encoding="utf-8")
    flat = load_account_budget(db, fy="FY2024-25")
    assert flat is not None
    assert flat.basis == "annual"
    assert flat.amounts == {"410000": money("2190000"), "Rent": money("182500")}

    sidecar.write_text(
        "budget_basis: to_date\naccounts:\n  FY2024-25:\n    Rent: 15000\n  FY2025-26:\n    Rent: 18000\n",
        encoding="utf-8",
    )
    by_year = load_account_budget(db, fy="FY2025-26")
    assert by_year is not None
    assert by_year.basis == "to_date"
    assert by_year.amounts == {"Rent": money("18000")}
    assert load_account_budget(db, fy="FY2030-31") is None

    sidecar.write_text("budget_basis: monthly\naccounts:\n  Rent: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="budget_basis"):
        load_account_budget(db, fy="FY2024-25")


def test_payload_and_excel_carry_variance_from_posted_books(tmp_path: Path) -> None:
    db = tmp_path / "ssdv_sample.sqlite"
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

    def payload() -> dict:
        with session_scope(engine) as session:
            snap = mis_snapshot(session, AS_OF)
            return enrich_payload(snapshot_payload(snap, "all"), session, db, AS_OF)

    assert payload()["budget_variance"] is None

    budget_sidecar_path(db).write_text(
        (EXAMPLE / "budget.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    data = payload()
    variance = data["budget_variance"]
    rows = {row["code"]: row for row in variance["rows"]}
    assert rows["410000"]["actual"] == "150000.00"
    assert rows["410000"]["budget"] == "180000.00"
    assert rows["410000"]["profit_impact"] == "-30000.00"
    assert rows["620000"]["actual"] == "20000.00"
    assert rows["620000"]["budget"] == "15000.00"
    assert rows["620000"]["favourable"] is False
    assert variance["profit_impact"] == "-35000.00"
    assert [row["code"] for row in variance["drivers"]] == ["410000", "620000"]
    # The existing sales-vs-budget line is unchanged.
    assert data["budget_vs_actual"]["sales_budget"] == "180000.00"

    out = tmp_path / "pack.xlsx"
    write_excel(data, out)
    sheet = load_workbook(out)["Budget variance"]
    cells = [[cell.value for cell in row] for row in sheet.iter_rows()]
    assert ["410000", "Sales", "income", "150000.00", "180000.00", "-30000.00", "-0.1667", "-30000.00", "no"] in cells
