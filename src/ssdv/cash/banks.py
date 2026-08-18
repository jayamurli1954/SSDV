from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ssdv.accounting.trial_balance import ledger_balance
from ssdv.gl import BANK_HDFC, BANK_ICICI, BANK_OD, CASH
from ssdv.money import ZERO, money

RECEIPT_BANKS = (BANK_HDFC, BANK_ICICI)
PAYMENT_BANKS = (BANK_HDFC, BANK_ICICI, BANK_OD)
ALL_BANKS = (CASH, BANK_HDFC, BANK_ICICI, BANK_OD)


def bank_floor(gl: str, od_limit: Decimal) -> Decimal:
    if gl == BANK_OD:
        return money(-od_limit)
    return ZERO


def current_bank_balances(session: Session, as_of: date) -> dict[str, Decimal]:
    return {gl: ledger_balance(session, gl, as_of) for gl in ALL_BANKS}


def choose_bank(
    balances: dict[str, Decimal],
    amount: Decimal,
    od_limit: Decimal,
    banks: tuple[str, ...] = PAYMENT_BANKS,
) -> str | None:
    amount = money(amount)
    for gl in banks:
        if money(balances[gl] - amount) >= bank_floor(gl, od_limit):
            return gl
    return None


def apply_bank(balances: dict[str, Decimal], gl: str, delta: Decimal) -> None:
    balances[gl] = money(balances[gl] + delta)
