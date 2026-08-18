from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ssdv.cli import build_parser, main
from ssdv.ingest import ingest_generic
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.mis.benchmarks import build_benchmarks
from ssdv.mis.packs import ceo_pack
from ssdv.mis.whatif import build_whatif
from ssdv.money import money
from ssdv.officemitra.boardpack import render_board_html, render_board_pdf
from ssdv.officemitra.charts import aging_points, monthly_series
from ssdv.officemitra.dashboard import render_dashboard
from ssdv.officemitra.insights import build_insights, build_red_flags, build_why
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def test_ceo_pack_has_fourteen_decision_tiles(session) -> None:
    ingest_generic(
        session,
        EXAMPLE / "journals.csv",
        EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
    )
    snap = mis_snapshot(session, date(2024, 4, 30))
    pack = ceo_pack(snap)
    ids = [tile.id for tile in pack.tiles]
    assert ids == [
        "sales",
        "gm",
        "cash",
        "ar",
        "ap",
        "inv",
        "working_capital",
        "monthly_profit",
        "collection_efficiency",
        "growth",
        "ccc",
        "current_ratio",
        "quick_ratio",
        "monthly_net_cash",
    ]
    assert snap.working_capital == money("139000")
    assert snap.current_assets == money("657000")
    assert snap.current_liabilities == money("27000")
    assert snap.current_ratio == Decimal("24.3333")
    assert snap.quick_ratio == Decimal("20.8370")
    assert snap.monthly_net_cash == money("23600")


def test_insights_are_in_line_on_pnl_and_aging(session) -> None:
    ingest_generic(
        session,
        EXAMPLE / "journals.csv",
        EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
    )
    snap = mis_snapshot(session, date(2024, 4, 30))
    items = build_insights(snap)
    surfaces = {item.surface for item in items}
    assert "pnl" in surfaces
    assert "aging" in surfaces
    texts = " ".join(item.text for item in items)
    assert "Gross margin" in texts
    assert "Collection efficiency" in texts
    payload = snapshot_payload(snap, "ceo")
    assert payload["insights"]
    assert payload["red_flags"] == []
    assert payload["why_prompts"]
    html = render_dashboard(payload)
    assert "OfficeMitra" in html
    assert "Sample Traders Pvt Ltd" in html
    assert "AR aging" in html
    assert "Board red flags" in html
    assert "Cash forecast" in html
    assert payload["benchmarks"]
    assert "Not a surveyed industry average" in payload["benchmark_source"]
    by_id = {row["id"]: row for row in payload["benchmarks"]}
    assert by_id["gross_margin"]["policy_status"] == "Hold"
    assert by_id["collection_efficiency"]["policy_status"] == "Breach"
    assert by_id["customer_share"]["policy_status"] == "Breach"
    assert by_id["dso"]["vs_peer"] == "No ABC baseline vault"
    assert "Benchmarks" in html
    assert payload["whatif"]
    assert payload["whatif_prompts"]
    assert "Recommend-only" in payload["whatif_method"]
    assert "What-if" in html
    wi = {row["id"]: row for row in payload["whatif"]}
    assert wi["collections_to_80"]["delta_inr"] == "2000.00"
    assert wi["sales_up_15"]["delta_inr"] == "22500.00"


def test_why_and_red_flags_from_posted_facts() -> None:
    series = SimpleNamespace(
        labels=("Apr-24", "May-24"),
        sales=(money("200000"), money("150000")),
        cogs=(money("80000"), money("90000")),
        gross_margin=(money("120000"), money("60000")),
        opex=(money("20000"), money("40000")),
        receipts=(money("180000"), money("50000")),
        payments=(money("40000"), money("40000")),
        purchases=(money("70000"), money("160000")),
    )
    snap = SimpleNamespace(
        series=series,
        monthly_profit=money("20000"),
        cash=money("-5000"),
        cash_blocked_90=money("80000"),
        ar=money("200000"),
        dso=160,
        dso_policy_gap_ar=money("50000"),
        equity=money("-1000"),
    )
    texts = " ".join(item.text for item in build_why(snap))
    assert "gross margin rupees fell" in texts
    assert "operating expenses rose" in texts
    assert "receipts fell" in texts
    assert "Cash sitting in AR 90+" in texts
    assert "extra AR vs policy" in texts
    assert "purchases" in texts
    assert "Cash position" in texts
    assert "CUST-" not in texts
    ids = {item.id for item in build_red_flags(snap)}
    assert ids == {"flag_dso", "flag_cash", "flag_equity", "flag_profit"}


def test_benchmarks_use_policy_and_abc_peer_not_industry() -> None:
    snap = SimpleNamespace(
        fy=SimpleNamespace(gm_pct=money("0.20")),
        dso=100,
        collection_efficiency=money("0.90"),
        current_ratio=money("1.50"),
        quick_ratio=money("1.20"),
        metrics=SimpleNamespace(
            inventory_to_sales=money("0.20"),
            top_customer_share=money("0.10"),
            cogs_ratio=money("0.80"),
        ),
        ccc=80,
    )
    peer = SimpleNamespace(
        fy=SimpleNamespace(gm_pct=money("0.18")),
        dso=110,
        collection_efficiency=money("0.85"),
        current_ratio=money("1.10"),
        quick_ratio=money("1.00"),
        metrics=SimpleNamespace(
            inventory_to_sales=money("0.30"),
            top_customer_share=money("0.20"),
            cogs_ratio=money("0.82"),
        ),
        ccc=90,
    )
    rows = {row.id: row for row in build_benchmarks(snap, peer)}
    assert rows["gross_margin"].policy_status == "Hold"
    assert "Better than ABC trading baseline" in rows["gross_margin"].vs_peer
    assert "industry" not in rows["gross_margin"].vs_peer.lower()
    assert rows["dso"].policy_status == "Hold"
    assert "Better than ABC trading baseline" in rows["dso"].vs_peer
    weak = SimpleNamespace(
        fy=SimpleNamespace(gm_pct=money("0.10")),
        dso=200,
        collection_efficiency=money("0.50"),
        current_ratio=money("0.80"),
        quick_ratio=money("0.50"),
        metrics=SimpleNamespace(
            inventory_to_sales=money("0.60"),
            top_customer_share=money("0.50"),
            cogs_ratio=money("0.90"),
        ),
        ccc=200,
    )
    weak_rows = {row.id: row for row in build_benchmarks(weak, None)}
    assert weak_rows["gross_margin"].policy_status == "Breach"
    assert weak_rows["dso"].vs_peer == "No ABC baseline vault"


def test_whatif_scenarios_use_posted_facts_only() -> None:
    snap = SimpleNamespace(
        dso=154,
        ar=money("54600000"),
        fy=SimpleNamespace(
            sales=money("100000000"),
            cogs=money("80000000"),
            opex=money("5000000"),
            receipts=money("70000000"),
        ),
        ytd_profit=money("15000000"),
        cash_blocked_90=money("33400000"),
        dso_policy_gap_ar=money("12000000"),
        metrics=SimpleNamespace(),
        series=SimpleNamespace(),
    )
    rows = {row.id: row for row in build_whatif(snap)}
    assert rows["dso_to_120"].delta_inr == money("12000000")
    assert "154" in rows["dso_to_120"].result
    assert rows["collect_ar90"].delta_inr == money("33400000")
    assert rows["sales_up_15"].delta_inr == money("3000000")
    assert rows["collections_to_80"].delta_inr == money("10000000")
    for row in rows.values():
        assert "industry" not in row.result.lower()


def test_dashboard_cli_writes_html(tmp_path: Path) -> None:
    db = tmp_path / "books.sqlite"
    html = tmp_path / "mis.html"
    assert (
        main(
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
        == 0
    )
    assert (
        main(
            [
                "--db",
                str(db),
                "dashboard",
                "--as-of",
                "2024-04-30",
                "--out",
                str(html),
            ]
        )
        == 0
    )
    text = html.read_text(encoding="utf-8")
    assert "CLI Traders" in text
    assert "OfficeMitra (on this screen)" in text
    pdf = tmp_path / "board-pack.pdf"
    assert (
        main(
            [
                "--db",
                str(db),
                "dashboard",
                "--pdf",
                "--as-of",
                "2024-04-30",
                "--out",
                str(pdf),
            ]
        )
        == 0
    )
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert b"%%EOF" in data
    assert b"CLI Traders" in data
    assert b"Board pack" in data


def test_board_pack_html_and_pdf_from_payload(session) -> None:
    ingest_generic(
        session,
        EXAMPLE / "journals.csv",
        EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
    )
    payload = snapshot_payload(mis_snapshot(session, date(2024, 4, 30)), "all")
    html = render_board_html(payload)
    assert "OfficeMitra Board pack" in html
    assert "Sample Traders Pvt Ltd" in html
    assert "Red flags" in html
    pdf = render_board_pdf(payload)
    assert pdf.startswith(b"%PDF-1.4")
    assert b"What-if" in pdf
    assert b"Benchmarks" in pdf


def test_dashboard_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(["dashboard", "--as-of", "2026-03-31", "--ask"])
    assert args.as_of == date(2026, 3, 31)
    assert args.ask is True
    pdf = parser.parse_args(["dashboard", "--pdf", "--as-of", "2026-03-31"])
    assert pdf.pdf is True
    mis = parser.parse_args(["mis", "--ask", "--json"])
    assert mis.ask is True
    assert mis.json is True
    ui = parser.parse_args(["ui", "--as-of", "2024-04-30"])
    assert ui.as_of == date(2024, 4, 30)
    assert ui.func.__name__ == "cmd_ui"


def test_chart_helpers_from_mis_json(session) -> None:
    ingest_generic(
        session,
        EXAMPLE / "journals.csv",
        EXAMPLE / "ledger_map.csv",
        company_name="Sample Traders Pvt Ltd",
    )
    payload = snapshot_payload(mis_snapshot(session, date(2024, 4, 30)), "all")
    labels, sales = monthly_series(payload, "sales")
    assert labels == ["Apr-24"]
    assert sales == [150000.0]
    aging = aging_points(payload, "ar_aging")
    assert {row["label"] for row in aging} >= {"0-30", "120+"}
    assert "cash_forecast" in payload
    assert payload["kpis"]["gst_input"] == "14400.00"
    assert payload["kpis"]["gst_net"] == "12600.00"
    fc = payload["cash_forecast"]
    assert fc["horizons"][0]["cash"] == "491000.00"
    assert fc["horizons"][2]["days"] == 90
    assert fc["blocked_ar"] == "59000.00"
    assert "current_ratio" in payload["kpis"]
    assert "monthly_net_cash" in payload["kpis"]
    assert payload["red_flags"] == []
