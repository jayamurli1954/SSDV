from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.accounting.subledger import ap_subledger, ar_subledger
from ssdv.cash.aging import AgingLine, ap_aging, ar_aging
from ssdv.models import Customer, Vendor
from ssdv.money import ZERO, money

TOP_N = 10
OVERDUE_BUCKETS = frozenset({"91-120", "120+"})
PARTIES_METHOD = (
    "Invoice aging 90+ where invoices exist. Journal parties with no invoice date are unaged. "
    "Customers ranked by AR 90+ (or largest AR if none). Vendors ranked by AP outstanding. "
    "Recommend-only; SSDV does not chase customers or pay vendors."
)


@dataclass(frozen=True)
class PartyExposure:
    code: str
    name: str
    outstanding: Decimal
    overdue_90: Decimal
    unaged: Decimal
    oldest_days: int | None
    share: Decimal


def _names(session: Session, model: type[Customer | Vendor]) -> dict[str, str]:
    return {str(row.code): str(row.name) for row in session.scalars(select(model))}


def _rollup(
    rows: list[AgingLine],
    subledger: dict[str, Decimal],
    names: dict[str, str],
    total: Decimal,
) -> list[PartyExposure]:
    aged: dict[str, Decimal] = {}
    overdue: dict[str, Decimal] = {}
    oldest: dict[str, int] = {}
    for row in rows:
        code = row.party_code
        aged[code] = money(aged.get(code, ZERO) + row.amount)
        if row.bucket in OVERDUE_BUCKETS:
            overdue[code] = money(overdue.get(code, ZERO) + row.amount)
        oldest[code] = max(oldest.get(code, 0), row.days)
    out: list[PartyExposure] = []
    for code in set(aged) | set(subledger):
        aged_amt = aged.get(code, ZERO)
        sub_amt = subledger.get(code, ZERO)
        outstanding = money(max(aged_amt, sub_amt))
        if outstanding <= ZERO:
            continue
        unaged = money(max(sub_amt - aged_amt, ZERO))
        share = (
            (outstanding / total).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if total > ZERO
            else ZERO
        )
        days = oldest.get(code)
        out.append(
            PartyExposure(
                code=code,
                name=names.get(code) or code,
                outstanding=outstanding,
                overdue_90=overdue.get(code, ZERO),
                unaged=unaged,
                oldest_days=days,
                share=share,
            )
        )
    return out


def _top_overdue(parties: list[PartyExposure], limit: int) -> tuple[list[PartyExposure], str]:
    overdue = [row for row in parties if row.overdue_90 > ZERO]
    overdue.sort(key=lambda row: (row.overdue_90, row.outstanding), reverse=True)
    if overdue:
        return overdue[:limit], "overdue_90"
    ranked = sorted(parties, key=lambda row: row.outstanding, reverse=True)
    return ranked[:limit], "outstanding"


def customer_vendor_tops(
    session: Session,
    as_of: date,
    *,
    limit: int = TOP_N,
) -> tuple[tuple[PartyExposure, ...], str, tuple[PartyExposure, ...]]:
    """Top overdue customers and top vendor AP exposure from posted books."""
    ar_rows = ar_aging(session, as_of)
    ap_rows = ap_aging(session, as_of)
    ar_sub = ar_subledger(session, as_of)
    ap_sub = ap_subledger(session, as_of)
    ar_total = money(sum(ar_sub.values(), ZERO))
    if ar_total <= ZERO:
        ar_total = money(sum((row.amount for row in ar_rows), ZERO))
    ap_total = money(sum(ap_sub.values(), ZERO))
    if ap_total <= ZERO:
        ap_total = money(sum((row.amount for row in ap_rows), ZERO))
    customers = _rollup(ar_rows, ar_sub, _names(session, Customer), ar_total)
    vendors = _rollup(ap_rows, ap_sub, _names(session, Vendor), ap_total)
    top_customers, rank = _top_overdue(customers, limit)
    top_vendors = sorted(vendors, key=lambda row: row.outstanding, reverse=True)[:limit]
    return tuple(top_customers), rank, tuple(top_vendors)
