from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.models import PurchaseBillLine, Product
from ssdv.money import money
from ssdv.purchases.generate import generate_purchases
from ssdv.sales.generate import generate_sales
from ssdv.scenarios import apply_scenario, record_scenario, scenario_metrics, signal_holds
from ssdv.scenarios.spec import GOLDEN
from ssdv.paths import load_company
from ssdv.cash.generate import generate_settlements
from ssdv.validate import run_gates


def _cfg(name: str):
    return apply_scenario(load_company(), name)


def test_customer_concentration_share(session) -> None:
    cfg = _cfg("customer_concentration")
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=30)
    generate_sales(session, company=cfg, target=40)
    metrics = scenario_metrics(session, date(2026, 3, 31), cfg)
    ok, _ = signal_holds(metrics, cfg)
    assert ok
    assert metrics.top_customer_share >= money("0.35")


def test_vendor_dependency_share(session) -> None:
    cfg = _cfg("vendor_dependency")
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=25)
    metrics = scenario_metrics(session, date(2026, 3, 31), cfg)
    ok, _ = signal_holds(metrics, cfg)
    assert ok
    assert metrics.top_vendor_share >= money("0.55")


def test_cash_flow_crisis_leaves_ar(session) -> None:
    cfg = _cfg("cash_flow_crisis")
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=12)
    generate_sales(session, company=cfg, target=8)
    generate_settlements(session, company=cfg, receipt_target=6, payment_target=4)
    metrics = scenario_metrics(session, date(2026, 3, 31), cfg)
    ok, _ = signal_holds(metrics, cfg)
    assert ok
    assert metrics.ar_to_sales >= money("0.30")


def test_margin_erosion_raises_purchase_rates(session) -> None:
    cfg = _cfg("margin_erosion")
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=15)
    products = {p.code: p for p in session.scalars(select(Product))}
    expensive = 0
    total = 0
    for line in session.scalars(select(PurchaseBillLine)):
        total += 1
        if line.rate >= money(products[line.product_code].cost_price * Decimal("1.05")):
            expensive += 1
    assert total > 0
    assert expensive / total >= 0.4


def test_inventory_buildup_ratio(session) -> None:
    cfg = _cfg("inventory_buildup")
    bootstrap_books(session, company=cfg)
    generate_purchases(session, company=cfg, target=20)
    generate_sales(session, company=cfg, target=6)
    metrics = scenario_metrics(session, date(2026, 3, 31), cfg)
    ok, _ = signal_holds(metrics, cfg)
    assert ok
    assert metrics.inventory_to_sales >= money("0.45")


def test_golden_strings_are_recorded(session) -> None:
    cfg = _cfg("customer_concentration")
    bootstrap_books(session, company=cfg)
    row = record_scenario(session, cfg)
    assert row.golden_explanation == GOLDEN["customer_concentration"]["golden"]
    gates = run_gates(session, date(2023, 4, 1), company=cfg)
    golden = next(g for g in gates if g.name == "scenario_golden")
    assert golden.ok
