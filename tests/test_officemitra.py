from datetime import date
from pathlib import Path

from ssdv.cli import build_parser, main
from ssdv.ingest import ingest_generic
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.mis.packs import ceo_pack
from ssdv.money import money
from ssdv.officemitra.charts import aging_points, monthly_series
from ssdv.officemitra.dashboard import render_dashboard
from ssdv.officemitra.insights import build_insights
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def test_ceo_pack_has_ten_decision_tiles(session) -> None:
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
    ]
    assert snap.working_capital == money("139000")


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
    html = render_dashboard(payload)
    assert "OfficeMitra" in html
    assert "Sample Traders Pvt Ltd" in html
    assert "AR aging" in html


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


def test_dashboard_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(["dashboard", "--as-of", "2026-03-31", "--ask"])
    assert args.as_of == date(2026, 3, 31)
    assert args.ask is True
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
    assert {row["label"] for row in aging} >= {"0-30", "90+"}
