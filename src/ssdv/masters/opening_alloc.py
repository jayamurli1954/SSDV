from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.allocate import allocate_total
from ssdv.gl import AP_CONTROL, AR_CONTROL, INVENTORY
from ssdv.models import Customer, Product, Vendor, Warehouse
from ssdv.money import ZERO, money
from ssdv.paths import load_company

QTY_ONE = Decimal(1)


def opening_amount(company: dict[str, Any], account_code: str) -> Decimal:
    return money(company["opening"][account_code])


def allocate_opening_ar(
    session: Session,
    rng,
    company: dict[str, Any] | None = None,
) -> list[tuple[Customer, Decimal]]:
    cfg = company or load_company()
    total = opening_amount(cfg, AR_CONTROL)
    customers = list(session.scalars(select(Customer).order_by(Customer.code)).all())
    core = [c for c in customers if c.tier == "core"]
    regular = [c for c in customers if c.tier == "regular"]
    rng.shuffle(regular)
    chosen = core + regular[:100]
    if not chosen:
        raise RuntimeError("No customers available for opening AR")
    weights = [float(c.credit_limit or 1) for c in chosen]
    amounts = allocate_total(weights, total)
    return [(c, amt) for c, amt in zip(chosen, amounts, strict=True) if amt > ZERO]


def allocate_opening_ap(
    session: Session,
    rng,
    company: dict[str, Any] | None = None,
) -> list[tuple[Vendor, Decimal]]:
    cfg = company or load_company()
    total = opening_amount(cfg, AP_CONTROL)
    vendors = list(session.scalars(select(Vendor).order_by(Vendor.code)).all())
    rng.shuffle(vendors)
    chosen = vendors[:80]
    weights = [1 / max(int(v.lead_time_days or 7), 1) for v in chosen]
    amounts = allocate_total(weights, total)
    return [(v, amt) for v, amt in zip(chosen, amounts, strict=True) if amt > ZERO]


def allocate_opening_stock(
    session: Session,
    rng,
    company: dict[str, Any] | None = None,
) -> list[tuple[Product, Warehouse, Decimal, Decimal, Decimal]]:
    """Return (product, warehouse, qty, rate, value) summing to inventory GL."""
    cfg = company or load_company()
    total = opening_amount(cfg, INVENTORY)
    products = list(session.scalars(select(Product).order_by(Product.code)).all())
    warehouses = list(session.scalars(select(Warehouse).order_by(Warehouse.code)).all())
    if not products or not warehouses:
        raise RuntimeError("Products and warehouses are required for opening stock")

    rng.shuffle(products)
    holders = products[: max(1, int(len(products) * 0.80))]
    weights = [1 / ((i + 1) ** 0.85) for i in range(len(holders))]
    allocated = allocate_total(weights, total)

    qtys: list[Decimal] = []
    for product, share in zip(holders, allocated, strict=True):
        raw = share / product.cost_price
        if product.uom == "MTR":
            qty = max(QTY_ONE, raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
        else:
            qty = max(QTY_ONE, raw.quantize(QTY_ONE, rounding=ROUND_HALF_UP))
        qtys.append(qty)

    values = [money(q * p.cost_price) for p, q in zip(holders, qtys, strict=True)]
    delta = money(total - sum(values, ZERO))
    idx = max(range(len(values)), key=lambda i: values[i])
    values[idx] = money(values[idx] + delta)
    if values[idx] <= ZERO:
        raise RuntimeError("Opening stock remainder could not be applied")
    rates = [p.cost_price for p in holders]
    rates[idx] = money(values[idx] / qtys[idx])

    wh_codes = warehouses
    weights_wh = [60, 25, 15][: len(wh_codes)]
    rows: list[tuple[Product, Warehouse, Decimal, Decimal, Decimal]] = []
    for product, qty, rate, value in zip(holders, qtys, rates, values, strict=True):
        warehouse = rng.choices(wh_codes, weights=weights_wh, k=1)[0]
        rows.append((product, warehouse, qty, rate, value))
    return rows
