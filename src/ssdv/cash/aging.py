from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.cash.outstanding import (
    bill_allocation_map,
    invoice_allocation_map,
    opening_ap_allocation_map,
    opening_ap_balances,
    opening_ar_allocation_map,
    opening_ar_balances,
)
from ssdv.models import PurchaseBill, SalesInvoice
from ssdv.money import ZERO, money
from ssdv.paths import load_company

BUCKETS = ("0-30", "31-60", "61-90", "91-120", "120+")


@dataclass(frozen=True)
class AgingLine:
    party_code: str
    doc_ref: str
    doc_date: date
    days: int
    bucket: str
    amount: Decimal


def _opening_date() -> date:
    return date.fromisoformat(str(load_company()["opening_as_of"]))


def bucket_for(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    if days <= 120:
        return "91-120"
    return "120+"


def ar_aging(session: Session, as_of: date) -> list[AgingLine]:
    rows: list[AgingLine] = []
    collected = invoice_allocation_map(session, as_of)
    invoices = session.scalars(
        select(SalesInvoice)
        .where(SalesInvoice.invoice_date <= as_of)
        .order_by(SalesInvoice.invoice_date)
    )
    for invoice in invoices:
        due = money(invoice.grand_total - collected.get(invoice.invoice_no, ZERO))
        if due <= ZERO:
            continue
        days = (as_of - invoice.invoice_date).days
        rows.append(
            AgingLine(
                party_code=invoice.customer_code,
                doc_ref=invoice.invoice_no,
                doc_date=invoice.invoice_date,
                days=days,
                bucket=bucket_for(days),
                amount=due,
            )
        )
    opening_date = _opening_date()
    opening_collected = opening_ar_allocation_map(session, as_of)
    for code, original in opening_ar_balances(session).items():
        due = money(original - opening_collected.get(code, ZERO))
        if due <= ZERO:
            continue
        days = max((as_of - opening_date).days, 0)
        rows.append(
            AgingLine(
                party_code=code,
                doc_ref="OPENING",
                doc_date=opening_date,
                days=days,
                bucket=bucket_for(days),
                amount=due,
            )
        )
    return rows


def ap_aging(session: Session, as_of: date) -> list[AgingLine]:
    rows: list[AgingLine] = []
    paid = bill_allocation_map(session, as_of)
    bills = session.scalars(
        select(PurchaseBill).where(PurchaseBill.bill_date <= as_of).order_by(PurchaseBill.bill_date)
    )
    for bill in bills:
        due = money(bill.grand_total - paid.get(bill.bill_no, ZERO))
        if due <= ZERO:
            continue
        days = (as_of - bill.bill_date).days
        rows.append(
            AgingLine(
                party_code=bill.vendor_code,
                doc_ref=bill.bill_no,
                doc_date=bill.bill_date,
                days=days,
                bucket=bucket_for(days),
                amount=due,
            )
        )
    opening_date = _opening_date()
    opening_paid = opening_ap_allocation_map(session, as_of)
    for code, original in opening_ap_balances(session).items():
        due = money(original - opening_paid.get(code, ZERO))
        if due <= ZERO:
            continue
        days = max((as_of - opening_date).days, 0)
        rows.append(
            AgingLine(
                party_code=code,
                doc_ref="OPENING",
                doc_date=opening_date,
                days=days,
                bucket=bucket_for(days),
                amount=due,
            )
        )
    return rows


def aging_totals(rows: list[AgingLine]) -> dict[str, Decimal]:
    totals = {name: ZERO for name in BUCKETS}
    for row in rows:
        totals[row.bucket] = money(totals[row.bucket] + row.amount)
    totals["90+"] = money(totals["91-120"] + totals["120+"])
    totals["total"] = money(sum((totals[name] for name in BUCKETS), ZERO))
    return totals
