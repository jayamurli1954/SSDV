from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.calendar import load_holidays, working_days
from ssdv.models import Product, PurchaseBill, Vendor, Warehouse
from ssdv.money import money
from ssdv.paths import load_company
from ssdv.purchases.posting import PurchaseLineInput, post_purchase
from ssdv.scenarios.spec import knobs

QTY_ONE = Decimal(1)
GROSS_MARGIN = Decimal("0.22")


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
        raise RuntimeError("Could not split purchase counts")
    return counts


def generate_purchases(
    session: Session,
    company: dict[str, Any] | None = None,
    target: int | None = None,
) -> int:
    cfg = company or load_company()
    target = int(target if target is not None else cfg["volumes"]["purchase_invoices"])
    existing = int(session.scalar(select(func.count()).select_from(PurchaseBill)) or 0)
    if existing >= target:
        return 0

    remaining = target - existing
    rng = random.Random(int(cfg["generator"]["seed"]) + 47)
    holidays = load_holidays(cfg)
    skip_sundays = bool(cfg["generator"].get("skip_sundays", True))
    extra = knobs(cfg)
    vendors = list(session.scalars(select(Vendor).order_by(Vendor.code)).all())
    products = list(session.scalars(select(Product).order_by(Product.code)).all())
    warehouses = list(session.scalars(select(Warehouse).order_by(Warehouse.code)).all())
    if not vendors or not products or not warehouses:
        raise RuntimeError("Masters must exist before generating purchases")

    ranked_vendors = vendors[:]
    rng.shuffle(ranked_vendors)
    whale_share = float(extra.get("vendor_whale_share") or 0)
    others = ranked_vendors[1:] or ranked_vendors
    other_weights = [1 / ((i + 1) ** 0.7) for i in range(len(others))]

    years = cfg["calendar"]["fiscal_years"]
    year_weights = [float(y["revenue_inr"]) for y in years]
    year_counts = _split_counts(year_weights, remaining)

    created = 0
    for year_i, (year, n_bills) in enumerate(zip(years, year_counts, strict=True)):
        if n_bills <= 0:
            continue
        start = date.fromisoformat(str(year["start"]))
        end = date.fromisoformat(str(year["end"]))
        if start == date.fromisoformat(str(cfg["opening_as_of"])):
            start = start + timedelta(days=1)
        days = working_days(start, end, skip_sundays=skip_sundays, holidays=holidays)
        if not days:
            raise RuntimeError(f"No working days in {year['code']}")

        purchase_value = money(Decimal(str(year["revenue_inr"])) * (Decimal(1) - GROSS_MARGIN))
        qty_mult = Decimal(str((extra.get("purchase_qty_multipliers") or [1, 1, 1])[year_i]))
        cost_mult = Decimal(str((extra.get("cost_multipliers") or [1, 1, 1])[year_i]))
        line_target = money(purchase_value / Decimal(n_bills * 3) * qty_mult)

        for i in range(n_bills):
            bill_date = days[int(i * len(days) / n_bills)]
            if whale_share and (i / max(n_bills, 1)) < whale_share:
                vendor = ranked_vendors[0]
            else:
                vendor = rng.choices(others, weights=other_weights, k=1)[0]
            warehouse = rng.choices(warehouses, weights=[60, 25, 15][: len(warehouses)], k=1)[0]
            n_lines = rng.randint(2, 6)
            chosen = rng.sample(products, k=min(n_lines, len(products)))
            lines: list[PurchaseLineInput] = []
            for product in chosen:
                rate = money(
                    product.cost_price * cost_mult * Decimal(str(round(rng.uniform(0.97, 1.04), 4)))
                )
                qty = _qty(line_target / rate, product.uom)
                lines.append(PurchaseLineInput(product=product, qty=qty, rate=rate))
            post_purchase(
                session,
                bill_date=bill_date,
                vendor=vendor,
                warehouse=warehouse,
                lines=lines,
                company=cfg,
            )
            created += 1
            if created % 100 == 0:
                session.flush()
    session.flush()
    return created
