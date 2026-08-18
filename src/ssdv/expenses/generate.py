from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.calendar import load_holidays, previous_working_day
from ssdv.cash.banks import choose_bank
from ssdv.expenses.posting import pay_opex, post_opex
from ssdv.fy import iter_month_ends
from ssdv.gl import (
    ELECTRICITY,
    EXPENSES_PAYABLE,
    FUEL,
    INSURANCE,
    OFFICE_EXPENSES,
    PROFESSIONAL_FEES,
    RENT,
    REPAIRS,
    SALARIES,
    SALARY_PAYABLE,
    STAFF_WELFARE,
    TELEPHONE,
)
from ssdv.models import Employee, OpexEntry
from ssdv.money import ZERO, money
from ssdv.paths import load_company

_OPEX_ROWS = (
    ("rent", RENT, "rent", Decimal("0")),
    ("electricity", ELECTRICITY, "electricity", Decimal("0.20")),
    ("telephone", TELEPHONE, "telephone", Decimal("0.10")),
    ("insurance", INSURANCE, "insurance", Decimal("0")),
    ("repairs", REPAIRS, "repairs", Decimal("0.40")),
    ("fuel", FUEL, "fuel", Decimal("0.25")),
    ("office", OFFICE_EXPENSES, "office", Decimal("0.15")),
    ("staff_welfare", STAFF_WELFARE, "staff_welfare", Decimal("0.20")),
)


def _jitter(rng: random.Random, base: Decimal, pct: Decimal) -> Decimal:
    if pct == ZERO:
        return money(base)
    factor = Decimal("1") + Decimal(str(rng.uniform(float(-pct), float(pct))))
    return money(base * factor)


def _payroll(session: Session, as_of: date) -> Decimal:
    total = ZERO
    for emp in session.scalars(select(Employee).where(Employee.is_active.is_(True))):
        if emp.joining_date is None or emp.joining_date <= as_of:
            total = money(total + emp.monthly_salary)
    return total


def generate_expenses(session: Session, company: dict[str, Any] | None = None) -> int:
    cfg = company or load_company()
    existing = int(session.scalar(select(func.count()).select_from(OpexEntry)) or 0)
    if existing > 0:
        return 0

    rng = random.Random(int(cfg["generator"]["seed"]) + 101)
    holidays = load_holidays(cfg)
    skip_sundays = bool(cfg["generator"].get("skip_sundays", True))
    books_start = date.fromisoformat(str(cfg["calendar"]["books_start"]))
    books_end = date.fromisoformat(str(cfg["calendar"]["books_end"]))
    opex = cfg["opex"]
    created = 0

    for month_end in iter_month_ends(books_start, books_end):
        when = previous_working_day(month_end, skip_sundays=skip_sundays, holidays=holidays)
        payroll = _payroll(session, when)
        if payroll > ZERO:
            post_opex(
                session,
                expense_date=when,
                kind="salary",
                account_code=SALARIES,
                amount=payroll,
                payable_gl=SALARY_PAYABLE,
                company=cfg,
            )
            created += 1
        for kind, account, yaml_key, pct in _OPEX_ROWS:
            amount = _jitter(rng, money(opex[yaml_key]), pct)
            if amount <= ZERO:
                continue
            post_opex(
                session,
                expense_date=when,
                kind=kind,
                account_code=account,
                amount=amount,
                payable_gl=EXPENSES_PAYABLE,
                company=cfg,
            )
            created += 1
        if when.month in {6, 9, 12, 3}:
            post_opex(
                session,
                expense_date=when,
                kind="professional",
                account_code=PROFESSIONAL_FEES,
                amount=money(opex["professional_quarterly"]),
                payable_gl=EXPENSES_PAYABLE,
                company=cfg,
            )
            created += 1
        if created % 40 == 0:
            session.flush()
    session.flush()
    return created


def pay_open_opex(
    session: Session,
    balances: dict[str, Decimal],
    od_limit: Decimal,
    as_of: date,
    company: dict[str, Any] | None = None,
) -> int:
    cfg = company or load_company()
    paid = 0
    open_rows = session.scalars(
        select(OpexEntry)
        .where(OpexEntry.paid_amount < OpexEntry.amount)
        .order_by(OpexEntry.expense_date, OpexEntry.id)
    )
    for entry in open_rows:
        due = money(entry.amount - entry.paid_amount)
        bank = choose_bank(balances, due, od_limit)
        if bank is None:
            continue
        pay_opex(session, entry, pay_date=as_of, bank_gl=bank, amount=due, company=cfg)
        balances[bank] = money(balances[bank] - due)
        paid += 1
    return paid
