from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.posting import PostingError
from ssdv.calendar import load_holidays, working_days
from ssdv.models import Customer, Product, SalesInvoice, StockMove, Warehouse
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.sales.posting import SalesLineInput, post_sale
from ssdv.scenarios.spec import knobs

QTY_ONE = Decimal("1")
TIER_WEIGHT = {"core": 8.0, "regular": 2.0, "occasional": 0.5}
BRANCH_WAREHOUSE = {
    "BR01": "WH-PUN",
    "BR02": "WH-MUM",
    "BR03": "WH-PUN",
    "BR04": "WH-NGP",
    "BR05": "WH-PUN",
}


@dataclass
class _Stock:
    qty: Decimal = ZERO
    value: Decimal = ZERO


def _qty(value: Decimal, uom: str) -> Decimal:
    if uom == "MTR":
        return max(QTY_ONE, value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
    return max(QTY_ONE, value.quantize(QTY_ONE, rounding=ROUND_HALF_UP))


def _split_counts(weights: list[float], total: int) -> list[int]:
    weight_sum = sum(weights)
    raw = [w / weight_sum * total for w in weights]
    counts = [int(x) for x in raw]
    counts[-1] = total - sum(counts[:-1])
    if counts[-1] < 0:
        raise RuntimeError("Could not split sales counts")
    return counts


def _apply_receipt(state: dict[str, _Stock], move: StockMove) -> None:
    bal = state.setdefault(move.product_code, _Stock())
    bal.qty += Decimal(move.qty_in)
    bal.value = money(bal.value + money(move.value))


def generate_sales(
    session: Session,
    company: dict[str, Any] | None = None,
    target: int | None = None,
) -> int:
    cfg = company or load_company()
    full_target = int(cfg["volumes"]["sales_invoices"])
    target = int(target if target is not None else full_target)
    existing = int(session.scalar(select(func.count()).select_from(SalesInvoice)) or 0)
    if existing >= target:
        return 0

    remaining = target - existing
    rng = random.Random(int(cfg["generator"]["seed"]) + 61)
    holidays = load_holidays(cfg)
    skip_sundays = bool(cfg["generator"].get("skip_sundays", True))
    extra = knobs(cfg)
    customers = list(session.scalars(select(Customer).order_by(Customer.code)).all())
    products = {p.code: p for p in session.scalars(select(Product)).all()}
    warehouses = {w.code: w for w in session.scalars(select(Warehouse)).all()}
    if not customers or not products or not warehouses:
        raise RuntimeError("Masters must exist before generating sales")

    whale = next((c for c in customers if c.tier == "core"), customers[0])
    whale_share = float(extra.get("sales_whale_share") or 0)
    cust_weights = [TIER_WEIGHT.get(c.tier or "occasional", 0.5) for c in customers]
    years = cfg["calendar"]["fiscal_years"]
    if extra.get("sales_year_weights"):
        year_weights = [float(w) for w in extra["sales_year_weights"]]
    else:
        year_weights = [float(y["revenue_inr"]) for y in years]
    full_counts = _split_counts(year_weights, full_target)
    year_counts = _split_counts(year_weights, remaining)

    receipts = list(
        session.scalars(
            select(StockMove)
            .where(StockMove.move_type.in_(("OPENING", "GRN")))
            .order_by(StockMove.move_date, StockMove.id)
        ).all()
    )
    state: dict[str, _Stock] = {}
    receipt_idx = 0
    created = 0

    def catch_up(as_of: date) -> None:
        nonlocal receipt_idx
        while receipt_idx < len(receipts) and receipts[receipt_idx].move_date <= as_of:
            _apply_receipt(state, receipts[receipt_idx])
            receipt_idx += 1

    for year_i, (year, n_bills, full_n) in enumerate(zip(years, year_counts, full_counts, strict=True)):
        if n_bills <= 0:
            continue
        start = date.fromisoformat(str(year["start"]))
        end = date.fromisoformat(str(year["end"]))
        if start == date.fromisoformat(str(cfg["opening_as_of"])):
            start = start + timedelta(days=1)
        days = working_days(start, end, skip_sundays=skip_sundays, holidays=holidays)
        if not days:
            raise RuntimeError(f"No working days in {year['code']}")
        revenue_base = years[0]["revenue_inr"] if extra.get("sales_flat_revenue") else year["revenue_inr"]
        bill_target = money(Decimal(str(revenue_base)) / Decimal(max(full_n, 1)))
        sell_mult = Decimal(str((extra.get("sell_multipliers") or [1, 1, 1])[year_i]))
        made = 0
        attempts = 0
        while made < n_bills and attempts < n_bills * 25:
            attempts += 1
            invoice_date = days[int(made * len(days) / n_bills) % len(days)]
            catch_up(invoice_date)
            in_stock = [p for p in products.values() if state.get(p.code, _Stock()).qty >= QTY_ONE]
            if not in_stock:
                continue
            if whale_share and (made / max(n_bills, 1)) < whale_share:
                customer = whale
            else:
                customer = rng.choices(customers, weights=cust_weights, k=1)[0]
            wh_code = BRANCH_WAREHOUSE.get(customer.branch_code or "BR01", "WH-PUN")
            warehouse = warehouses[wh_code]
            n_lines = rng.randint(1, 4)
            chosen = rng.sample(in_stock, k=min(n_lines, len(in_stock)))
            lines: list[SalesLineInput] = []
            remaining_target = bill_target
            for product in chosen:
                bal = state[product.code]
                rate = money(
                    product.selling_price
                    * sell_mult
                    * Decimal(str(round(rng.uniform(0.98, 1.04), 4)))
                )
                want = _qty(remaining_target / rate / Decimal(max(len(chosen), 1)), product.uom)
                qty = min(want, bal.qty)
                if product.uom != "MTR":
                    qty = qty.quantize(QTY_ONE, rounding=ROUND_HALF_UP)
                else:
                    qty = qty.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                if qty < QTY_ONE:
                    continue
                if qty > bal.qty:
                    qty = bal.qty if product.uom == "MTR" else bal.qty.quantize(QTY_ONE)
                if qty < QTY_ONE:
                    continue
                lines.append(SalesLineInput(product=product, qty=qty, rate=rate))
            if not lines:
                continue
            try:
                invoice = post_sale(
                    session,
                    invoice_date=invoice_date,
                    customer=customer,
                    warehouse=warehouse,
                    lines=lines,
                    company=cfg,
                )
            except PostingError:
                continue
            for line in invoice.lines:
                bal = state[line.product_code]
                bal.qty -= Decimal(line.qty)
                bal.value = money(bal.value - money(line.cogs_value))
            made += 1
            created += 1
            if created % 100 == 0:
                session.flush()
        if made < n_bills:
            raise RuntimeError(
                f"Only created {made} of {n_bills} sales invoices in {year['code']} (stock constrained)"
            )
    session.flush()
    return created
