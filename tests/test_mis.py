from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ssdv.accounting.activity import voucher_account_net
from ssdv.accounting.opening import bootstrap_books
from ssdv.cli import build_parser
from ssdv.gl import SALES
from ssdv.inventory.stock import stock_quantity
from ssdv.mis import dumps_snapshot, mis_snapshot, render_mis, scorecard, snapshot_payload
from ssdv.mis.packs import ceo_pack
from ssdv.models import Customer, Product, VoucherType, Warehouse
from ssdv.money import money
from ssdv.paths import load_company
from ssdv.purchases.generate import generate_purchases
from ssdv.sales.generate import generate_sales
from ssdv.sales.posting import SalesLineInput, post_sale
from ssdv.scenarios import apply_scenario


def _cfg(name: str = "baseline"):
    return apply_scenario(load_company(), name)


def _stocked_product(session, min_qty: Decimal = Decimal(20)) -> Product:
    as_of = date(2026, 3, 31)
    for product in session.scalars(select(Product).order_by(Product.code)):
        if stock_quantity(session, as_of, product.code) >= min_qty:
            return product
    raise AssertionError("No product with enough stock")


def test_mis_ytd_reads_sale_vouchers(session) -> None:
    cfg = _cfg()
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=8)
    product = _stocked_product(session)
    warehouse = session.scalars(select(Warehouse).limit(1)).first()
    customer = session.scalars(select(Customer).limit(1)).first()
    assert warehouse is not None and customer is not None
    qty = Decimal(2)
    first = post_sale(
        session,
        invoice_date=date(2023, 6, 15),
        customer=customer,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=qty, rate=money(product.selling_price))],
        company=cfg,
    )
    second = post_sale(
        session,
        invoice_date=date(2024, 6, 15),
        customer=customer,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=qty, rate=money(product.selling_price))],
        company=cfg,
    )

    y1 = mis_snapshot(session, date(2024, 3, 31), company=cfg)
    assert y1.fy.fy_code == "FY2023-24"
    assert y1.fy.sales == first.taxable
    assert y1.fy.sales == money(
        -voucher_account_net(
            session, SALES, date(2024, 3, 31), (VoucherType.SALE.value,), since=date(2023, 4, 1)
        )
    )
    assert y1.equation.holds
    assert y1.dso is not None
    assert y1.series.grain == "month"
    assert "2023-06" in y1.series.categories
    june = y1.series.categories.index("2023-06")
    assert y1.series.labels[june] == "Jun-23"
    assert y1.series.sales[june] == first.taxable
    assert sum(y1.series.sales, money(0)) == y1.fy.sales

    y2 = mis_snapshot(session, date(2025, 3, 31), company=cfg)
    assert y2.fy.fy_code == "FY2024-25"
    assert y2.fy.sales == second.taxable
    assert y2.prior is not None
    assert y2.prior.sales == first.taxable
    assert y2.sales_growth is not None


def test_mis_json_and_packs(session) -> None:
    cfg = _cfg()
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=6)
    generate_sales(session, company=cfg, target=5)
    snap = mis_snapshot(session, date(2026, 3, 31), company=cfg)
    payload = snapshot_payload(snap, "all")
    assert payload["scenario"] == "baseline"
    assert {p["id"] for p in payload["packs"]} == {"ceo", "cfo", "board"}
    assert "sales" in payload["kpis"]
    assert payload["series"]["grain"] == "month"
    assert len(payload["series"]["categories"]) == len(payload["series"]["sales"])
    monthly = payload["charts"]["monthly"]
    assert monthly["type"] == "line"
    assert monthly["series"][0]["id"] == "sales"
    assert len(monthly["categories"]) == len(monthly["series"][0]["data"])
    assert payload["charts"]["ar_aging"]["type"] == "doughnut"
    assert payload["charts"]["pnl_mix"]["type"] == "pie"
    assert "working_capital" in payload["kpis"]
    assert "collection_efficiency" in payload["kpis"]
    assert "current_ratio" in payload["kpis"]
    assert "quick_ratio" in payload["kpis"]
    assert "monthly_net_cash" in payload["kpis"]
    assert payload["insights"]
    assert "red_flags" in payload
    assert payload["why_prompts"]
    assert "cash_forecast" in payload
    assert payload["cash_forecast"]["horizons"][0]["days"] == 30
    assert "gst_net" in payload["kpis"]
    assert payload["benchmarks"]
    assert "Not a surveyed industry average" in payload["benchmark_source"]
    assert payload["whatif"]
    assert payload["parties"]["overdue_customers"]
    assert payload["parties"]["overdue_customers"][0]["outstanding"]
    assert payload["parties"]["vendor_exposure"]
    assert len(payload["whatif"]) == 4
    ceo = next(p for p in payload["packs"] if p["id"] == "ceo")
    assert {t["id"] for t in ceo["tiles"]} >= {
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
    }
    text = render_mis(snap, "ceo")
    assert "OfficeMitra" in text
    assert dumps_snapshot(snap, "ceo")
    text = render_mis(snap, "ceo")
    assert "CEO pack" in text
    assert "Top overdue customers" in text
    assert snap.company_name in text
    board_text = render_mis(snap, "board")
    assert "Benchmarks" in board_text
    assert "SSDV policy" in board_text
    cfo = next(p for p in payload["packs"] if p["id"] == "cfo")
    assert {t["id"] for t in cfo["tiles"]} >= {
        "cash_30",
        "cash_60",
        "cash_90",
        "gst_input",
        "gst_output",
    }


def test_concentration_scorecard_breach(session) -> None:
    cfg = _cfg("customer_concentration")
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=30)
    generate_sales(session, company=cfg, target=40)
    snap = mis_snapshot(session, date(2026, 3, 31), company=cfg)
    rows = {row.id: row for row in scorecard(snap)}
    assert rows["customer_concentration"].status == "Breach"
    pack = ceo_pack(snap)
    assert any(tile.id == "working_capital" for tile in pack.tiles)
    assert rows["customer_concentration"].tone == "danger"


def test_mis_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(["mis", "--pack", "cfo", "--json", "--as-of", "2026-03-31"])
    assert args.pack == "cfo"
    assert args.json is True
    assert args.as_of == date(2026, 3, 31)
