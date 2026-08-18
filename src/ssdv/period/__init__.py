from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.banking.generate import generate_banking
from ssdv.cash.banks import current_bank_balances
from ssdv.close.generate import generate_yearend
from ssdv.expenses.generate import generate_expenses, pay_open_opex
from ssdv.models import Voucher, VoucherType
from ssdv.money import money
from ssdv.paths import load_company
from ssdv.tax.generate import generate_gst


@dataclass(frozen=True)
class BooksSummary:
    expenses: int
    charges: int
    emis: int
    gst: int
    opex_paid: int
    depreciation: int
    closing: int


def generate_books(session: Session, company: dict[str, Any] | None = None) -> BooksSummary:
    cfg = company or load_company()
    books_end = date.fromisoformat(str(cfg["calendar"]["books_end"]))
    od_limit = money(cfg["accounting"]["od_limit_inr"])

    expenses = generate_expenses(session, company=cfg)
    charges, emis = generate_banking(session, company=cfg)
    gst = generate_gst(session, company=cfg)

    already_closed = (
        session.scalar(
            select(func.count())
            .select_from(Voucher)
            .where(Voucher.voucher_type == VoucherType.CLOSING.value)
        )
        or 0
    )
    opex_paid = 0
    if int(already_closed) == 0:
        balances = current_bank_balances(session, books_end)
        opex_paid = pay_open_opex(session, balances, od_limit, books_end, company=cfg)

    depreciation, closing = generate_yearend(session, company=cfg)
    return BooksSummary(
        expenses=expenses,
        charges=charges,
        emis=emis,
        gst=gst,
        opex_paid=opex_paid,
        depreciation=depreciation,
        closing=closing,
    )
