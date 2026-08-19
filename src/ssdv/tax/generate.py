from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.calendar import load_holidays, next_working_day
from ssdv.cash.banks import apply_bank, choose_bank, current_bank_balances
from ssdv.fy import iter_month_ends
from ssdv.models import GstSettlement, PurchaseBill, SalesInvoice
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.tax.posting import post_gst_settlement


def _sum_tax(
    session: Session, model, date_col, start: date, end: date
) -> tuple[Decimal, Decimal, Decimal]:
    cgst = money(
        session.scalar(
            select(func.coalesce(func.sum(model.cgst), 0)).where(date_col >= start, date_col <= end)
        )
        or 0
    )
    sgst = money(
        session.scalar(
            select(func.coalesce(func.sum(model.sgst), 0)).where(date_col >= start, date_col <= end)
        )
        or 0
    )
    igst = money(
        session.scalar(
            select(func.coalesce(func.sum(model.igst), 0)).where(date_col >= start, date_col <= end)
        )
        or 0
    )
    return cgst, sgst, igst


def generate_gst(session: Session, company: dict[str, Any] | None = None) -> int:
    cfg = company or load_company()
    if int(session.scalar(select(func.count()).select_from(GstSettlement)) or 0) > 0:
        return 0

    holidays = load_holidays(cfg)
    skip_sundays = bool(cfg["generator"].get("skip_sundays", True))
    books_start = date.fromisoformat(str(cfg["calendar"]["books_start"]))
    books_end = date.fromisoformat(str(cfg["calendar"]["books_end"]))
    od_limit = money(cfg["accounting"]["od_limit_inr"])
    balances = current_bank_balances(session, books_end)
    created = 0

    for period_end in iter_month_ends(books_start, books_end):
        start = date(period_end.year, period_end.month, 1)
        out_c, out_s, out_i = _sum_tax(
            session, SalesInvoice, SalesInvoice.invoice_date, start, period_end
        )
        in_c, in_s, in_i = _sum_tax(
            session, PurchaseBill, PurchaseBill.bill_date, start, period_end
        )
        if out_c + out_s + out_i + in_c + in_s + in_i == ZERO:
            continue
        if out_c + out_s + out_i == ZERO:
            continue
        if period_end.month == 12:
            due = date(period_end.year + 1, 1, 20)
        else:
            due = date(period_end.year, period_end.month + 1, 20)
        when = next_working_day(due, books_end, skip_sundays=skip_sundays, holidays=holidays)
        if when is None:
            when = books_end

        itc_c = min(in_c, out_c)
        itc_s = min(in_s, out_s)
        itc_i = min(in_i, out_i)
        payable = money((out_c - itc_c) + (out_s - itc_s) + (out_i - itc_i))
        bank = None
        paid = ZERO
        if payable > ZERO:
            bank = choose_bank(balances, payable, od_limit)
            if bank is not None:
                paid = payable
        period = f"{period_end.year:04d}-{period_end.month:02d}"
        post_gst_settlement(
            session,
            period=period,
            period_end=period_end,
            settlement_date=when,
            output_cgst=out_c,
            output_sgst=out_s,
            output_igst=out_i,
            input_cgst=in_c,
            input_sgst=in_s,
            input_igst=in_i,
            paid=paid,
            bank_gl=bank,
            company=cfg,
        )
        if bank is not None and paid > ZERO:
            apply_bank(balances, bank, money(-paid))
        created += 1
        session.flush()
    return created
