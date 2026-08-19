from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.posting import PostingError
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.calendar import load_holidays, next_working_day
from ssdv.cash.outstanding import opening_ap_balances, opening_ar_balances
from ssdv.cash.posting import post_payment, post_receipt
from ssdv.gl import BANK_HDFC, BANK_ICICI, BANK_OD, CASH
from ssdv.models import Customer, Payment, PurchaseBill, Receipt, SalesInvoice, Vendor
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.scenarios.spec import knobs

RECEIPT_BANKS = (BANK_HDFC, BANK_ICICI)
PAYMENT_BANKS = (BANK_HDFC, BANK_ICICI, BANK_OD)


def _delay_days(rng: random.Random, base: int, bucket: str) -> int | None:
    if bucket == "overdue":
        return None
    base = max(int(base), 7)
    if bucket == "early":
        return max(7, base - 10)
    if bucket == "late":
        return base + 30
    return base


def _pick_bucket(rng: random.Random, weights: list[int] | None = None) -> str:
    return rng.choices(
        ["early", "ontime", "late", "overdue"],
        weights=weights or [40, 35, 15, 10],
        k=1,
    )[0]


def _bank_floor(gl: str, od_limit: Decimal) -> Decimal:
    if gl == BANK_OD:
        return money(-od_limit)
    return ZERO


def generate_settlements(
    session: Session,
    company: dict[str, Any] | None = None,
    receipt_target: int | None = None,
    payment_target: int | None = None,
) -> tuple[int, int]:
    cfg = company or load_company()
    receipt_target = int(
        receipt_target if receipt_target is not None else cfg["volumes"]["receipts"]
    )
    payment_target = int(
        payment_target if payment_target is not None else cfg["volumes"]["payments"]
    )
    existing_r = int(session.scalar(select(func.count()).select_from(Receipt)) or 0)
    existing_p = int(session.scalar(select(func.count()).select_from(Payment)) or 0)
    if existing_r > 0 or existing_p > 0:
        return 0, 0

    rng = random.Random(int(cfg["generator"]["seed"]) + 83)
    extra = knobs(cfg)
    collect_weights = list(extra.get("collection_weights") or [40, 35, 15, 10])
    opening_ar_rate = float(extra.get("opening_ar_collect") or 0.80)
    holidays = load_holidays(cfg)
    skip_sundays = bool(cfg["generator"].get("skip_sundays", True))
    books_end = date.fromisoformat(str(cfg["calendar"]["books_end"]))
    opening_date = date.fromisoformat(str(cfg["opening_as_of"]))
    od_limit = money(cfg["accounting"]["od_limit_inr"])

    customers = {c.code: c for c in session.scalars(select(Customer)).all()}
    vendors = {v.code: v for v in session.scalars(select(Vendor)).all()}
    invoices = list(
        session.scalars(
            select(SalesInvoice).order_by(SalesInvoice.invoice_date, SalesInvoice.id)
        ).all()
    )
    bills = list(
        session.scalars(
            select(PurchaseBill).order_by(PurchaseBill.bill_date, PurchaseBill.id)
        ).all()
    )

    planned: list[tuple[date, int, Literal["receipt", "payment"], dict[str, Any]]] = []
    seq = 0

    def add_event(when: date, kind: Literal["receipt", "payment"], payload: dict[str, Any]) -> None:
        nonlocal seq
        seq += 1
        planned.append((when, seq, kind, payload))

    # Opening AR collections (~80%).
    for code, due in opening_ar_balances(session).items():
        if rng.random() > opening_ar_rate:
            continue
        delay = rng.randint(10, 40)
        when = next_working_day(
            opening_date + timedelta(days=delay),
            books_end,
            skip_sundays=skip_sundays,
            holidays=holidays,
        )
        if when is None:
            continue
        add_event(
            when,
            "receipt",
            {"customer": customers[code], "amount": due, "allocations": [(None, due)]},
        )

    for invoice in invoices:
        bucket = _pick_bucket(rng, collect_weights)
        delay = _delay_days(rng, customers[invoice.customer_code].credit_days or 30, bucket)
        if delay is None:
            continue
        when = next_working_day(
            invoice.invoice_date + timedelta(days=delay),
            books_end,
            skip_sundays=skip_sundays,
            holidays=holidays,
        )
        if when is None:
            continue
        add_event(
            when,
            "receipt",
            {
                "customer": customers[invoice.customer_code],
                "amount": invoice.grand_total,
                "allocations": [(invoice.invoice_no, invoice.grand_total)],
            },
        )

    # Opening AP payments (~75%).
    for code, due in opening_ap_balances(session).items():
        if rng.random() > 0.75:
            continue
        delay = rng.randint(15, 40)
        when = next_working_day(
            opening_date + timedelta(days=delay),
            books_end,
            skip_sundays=skip_sundays,
            holidays=holidays,
        )
        if when is None:
            continue
        add_event(
            when,
            "payment",
            {"vendor": vendors[code], "amount": due, "allocations": [(None, due)]},
        )

    for bill in bills:
        bucket = _pick_bucket(rng, collect_weights)
        delay = _delay_days(rng, vendors[bill.vendor_code].payment_days or 30, bucket)
        if delay is None:
            continue
        when = next_working_day(
            bill.bill_date + timedelta(days=delay),
            books_end,
            skip_sundays=skip_sundays,
            holidays=holidays,
        )
        if when is None:
            continue
        amount = bill.grand_total
        if rng.random() < 0.50 and amount > money("20000"):
            first = money(amount * Decimal("0.60"))
            second = money(amount - first)
            second_when = next_working_day(
                when + timedelta(days=14),
                books_end,
                skip_sundays=skip_sundays,
                holidays=holidays,
            )
            add_event(
                when,
                "payment",
                {
                    "vendor": vendors[bill.vendor_code],
                    "amount": first,
                    "allocations": [(bill.bill_no, first)],
                },
            )
            if second_when is not None and second > ZERO:
                add_event(
                    second_when,
                    "payment",
                    {
                        "vendor": vendors[bill.vendor_code],
                        "amount": second,
                        "allocations": [(bill.bill_no, second)],
                    },
                )
        else:
            add_event(
                when,
                "payment",
                {
                    "vendor": vendors[bill.vendor_code],
                    "amount": amount,
                    "allocations": [(bill.bill_no, amount)],
                },
            )

    planned.sort(key=lambda item: (item[0], 0 if item[2] == "receipt" else 1, item[1]))

    balances = {
        CASH: ledger_balance(session, CASH, books_end),
        BANK_HDFC: ledger_balance(session, BANK_HDFC, books_end),
        BANK_ICICI: ledger_balance(session, BANK_ICICI, books_end),
        BANK_OD: ledger_balance(session, BANK_OD, books_end),
    }

    created_r = 0
    created_p = 0
    deferred_payments: list[dict[str, Any]] = []
    for when, _seq, kind, payload in planned:
        if kind == "receipt":
            if created_r >= receipt_target:
                continue
            bank = rng.choice(RECEIPT_BANKS)
            try:
                post_receipt(
                    session,
                    receipt_date=when,
                    customer=payload["customer"],
                    bank_gl=bank,
                    amount=payload["amount"],
                    allocations=payload["allocations"],
                    company=cfg,
                )
            except PostingError:
                continue
            balances[bank] = money(balances[bank] + payload["amount"])
            created_r += 1
            if created_r % 100 == 0:
                session.flush()
        else:
            if created_p >= payment_target:
                continue
            amount = payload["amount"]
            chosen = None
            for gl in PAYMENT_BANKS:
                if money(balances[gl] - amount) >= _bank_floor(gl, od_limit):
                    chosen = gl
                    break
            if chosen is None:
                deferred_payments.append(payload)
                continue
            try:
                post_payment(
                    session,
                    payment_date=when,
                    vendor=payload["vendor"],
                    bank_gl=chosen,
                    amount=amount,
                    allocations=payload["allocations"],
                    company=cfg,
                )
            except PostingError:
                continue
            balances[chosen] = money(balances[chosen] - amount)
            created_p += 1
            if created_p % 100 == 0:
                session.flush()

    for payload in deferred_payments:
        if created_p >= payment_target:
            break
        amount = payload["amount"]
        chosen = None
        for gl in PAYMENT_BANKS:
            if money(balances[gl] - amount) >= _bank_floor(gl, od_limit):
                chosen = gl
                break
        if chosen is None:
            continue
        try:
            post_payment(
                session,
                payment_date=books_end,
                vendor=payload["vendor"],
                bank_gl=chosen,
                amount=amount,
                allocations=payload["allocations"],
                company=cfg,
            )
        except PostingError:
            continue
        balances[chosen] = money(balances[chosen] - amount)
        created_p += 1
    session.flush()
    return created_r, created_p
