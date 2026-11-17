from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ssdv.connectors.pipeline import load_into_vault
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.mis.runway import (
    Levers,
    base_as_dict,
    base_from_dict,
    runway_base,
    runway_months,
    simulate_runway,
)
from ssdv.money import ZERO, money
from ssdv.officemitra.firm import ClientSummary, _triage_key, build_roster, render_firm_html
from ssdv.officemitra.risk import AMBER, GREEN, RED, assess_risk
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def _snap(
    *,
    sales: tuple[str, ...],
    cogs: tuple[str, ...],
    opex: tuple[str, ...],
    cash: str,
    as_of: date = date(2026, 3, 31),
    ar: str = "600000",
    dso: int | None = 40,
    equity: str = "1000000",
) -> SimpleNamespace:
    series = SimpleNamespace(
        sales=tuple(money(v) for v in sales),
        cogs=tuple(money(v) for v in cogs),
        opex=tuple(money(v) for v in opex),
    )
    last = money(series.sales[-1] - series.cogs[-1] - series.opex[-1])
    return SimpleNamespace(
        as_of=as_of,
        series=series,
        cash=money(cash),
        ar=money(ar),
        dso=dso,
        equity=money(equity),
        monthly_profit=last,
    )


def _burning(cash: str, **kwargs) -> SimpleNamespace:
    # Flat loss of 1,00,000 a month, so profit is not falling month on month.
    return _snap(
        sales=("500000", "500000", "500000"),
        cogs=("400000", "400000", "400000"),
        opex=("200000", "200000", "200000"),
        cash=cash,
        **kwargs,
    )


def test_runway_months_edges() -> None:
    assert runway_months(money("500000"), ZERO) is None
    assert runway_months(money("-10"), money("100")) == Decimal("0.0")
    assert runway_months(money("250000"), money("100000")) == Decimal("2.5")


def test_base_averages_last_three_complete_months() -> None:
    snap = _snap(
        sales=("900000", "300000", "600000", "600000", "50000"),
        cogs=("0", "200000", "400000", "600000", "40000"),
        opex=("0", "100000", "100000", "100000", "5000"),
        cash="900000",
        as_of=date(2026, 3, 10),
    )
    base = runway_base(snap)
    # The first month is outside the window and the part month of March is dropped.
    assert base.months_used == 3
    assert base.partial_month is False
    assert base.monthly_sales == money("500000")
    assert base.monthly_cogs == money("400000")
    assert base.monthly_result == money("0")
    assert base.runway is None


def test_single_part_month_is_used_and_marked() -> None:
    snap = _snap(sales=("100",), cogs=("50",), opex=("80",), cash="300", as_of=date(2026, 3, 10))
    base = runway_base(snap)
    assert base.months_used == 1
    assert base.partial_month is True
    assert base.burn == money("30")
    assert base.runway == Decimal("10.0")


def test_simulation_levers_move_runway() -> None:
    base = runway_base(_burning("250000"))
    before, same = simulate_runway(base, Levers())
    assert before == same
    assert before.burn == money("100000")
    assert before.runway == Decimal("2.5")

    _, after = simulate_runway(
        base,
        Levers(
            sales_change_pct=Decimal(10),
            opex_change_pct=Decimal(-10),
            new_monthly_cost=money("15000"),
            ar_collected=money("9999999"),
        ),
    )
    # Sales 5.5L, COGS 4.4L at the same margin, opex 1.8L + 0.15L hire.
    assert after.monthly_result == money("-85000")
    assert after.burn == money("85000")
    # Collections are capped at the 6L of AR on the books.
    assert after.cash == money("850000")
    assert after.runway == Decimal("10.0")

    _, profitable = simulate_runway(base, Levers(sales_change_pct=Decimal(100)))
    assert profitable.burn == ZERO
    assert profitable.runway is None


def test_base_round_trips_through_payload_dict() -> None:
    base = runway_base(_burning("250000"))
    assert base_from_dict(base_as_dict(base)) == base


def test_risk_bands_follow_runway_and_board_flags() -> None:
    red = assess_risk(_burning("250000"))
    assert red.band == RED
    assert "2.5 months" in red.top_alert

    amber = assess_risk(_burning("450000"))
    assert amber.band == AMBER
    assert "below 6 months" in amber.top_alert

    green = assess_risk(
        _snap(
            sales=("500000", "500000"),
            cogs=("300000", "300000"),
            opex=("100000", "100000"),
            cash="100000",
        )
    )
    assert green.band == GREEN
    assert green.reasons == ()
    assert green.top_alert == "No board exceptions."

    # A board red flag alone (DSO over policy) is enough for red.
    slow = assess_risk(
        _snap(
            sales=("500000", "500000"),
            cogs=("300000", "300000"),
            opex=("100000", "100000"),
            cash="100000",
            dso=200,
        )
    )
    assert slow.band == RED
    assert "DSO 200" in slow.top_alert


def test_roster_sorts_worst_first() -> None:
    def row(name: str, risk: str, runway: str | None, error: str | None = None) -> ClientSummary:
        return ClientSummary(
            db_path=Path(f"{name}.sqlite"),
            vault_label=name,
            company=name,
            sales=ZERO,
            cash=ZERO,
            ar_90=ZERO,
            working_capital=ZERO,
            ar=ZERO,
            error=error,
            risk=risk,
            runway_months=None if runway is None else Decimal(runway),
        )

    rows = [
        row("Healthy", GREEN, None),
        row("Watch", AMBER, "5.0"),
        row("Red long", RED, None),
        row("Red short", RED, "1.2"),
        row("Broken", "", None, error="cannot open"),
    ]
    ordered = [item.company for item in sorted(rows, key=_triage_key)]
    assert ordered == ["Broken", "Red short", "Red long", "Watch", "Healthy"]


def test_roster_and_payload_carry_risk_from_posted_books(tmp_path: Path, session) -> None:
    for name in ("Alpha Traders", "Beta Traders"):
        load_into_vault(
            tmp_path / f"ssdv_{name.split()[0].lower()}.sqlite",
            source="generic",
            journals=EXAMPLE / "journals.csv",
            account_map=EXAMPLE / "ledger_map.csv",
            company_name=name,
            force=True,
        )
    roster = build_roster(date(2024, 4, 30), data_dir=tmp_path, limit=20)
    assert [row.company for row in roster.rows] == ["Alpha Traders", "Beta Traders"]
    assert all(row.risk in {RED, AMBER, GREEN} and row.top_alert for row in roster.rows)
    html = render_firm_html(roster)
    assert "Top alert" in html
    assert "Runway" in html

    from ssdv.ingest import ingest_generic

    ingest_generic(
        session,
        EXAMPLE / "journals.csv",
        EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
    )
    payload = snapshot_payload(mis_snapshot(session, date(2024, 4, 30)), "ceo")
    runway = payload["runway"]
    assert runway["risk"] == roster.rows[0].risk
    assert runway["months_used"] >= 1
    assert "Books are not changed" in runway["method"]
