from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ssdv.accounting.trial_balance import trial_balance
from ssdv.money import ZERO, money

_DEBIT_NATIVE = {"asset", "expense"}
_CREDIT_NATIVE = {"liability", "equity", "income"}


@dataclass(frozen=True)
class EquationSnapshot:
    as_of: date
    assets: Decimal
    liabilities: Decimal
    equity: Decimal
    income: Decimal
    expenses: Decimal
    delta: Decimal

    @property
    def holds(self) -> bool:
        return self.delta == ZERO


def accounting_equation(session: Session, as_of: date) -> EquationSnapshot:
    """Assets = Liabilities + Equity + (Income - Expenses). Contra-assets reduce assets."""
    assets = ZERO
    liabilities = ZERO
    equity = ZERO
    income = ZERO
    expenses = ZERO

    for row in trial_balance(session, as_of):
        if row.account_type == "asset" and row.subtype == "contra_asset":
            assets -= row.credit
            assets += row.debit  # unusual, but keep signed
            continue
        if row.account_type in _DEBIT_NATIVE:
            signed = money(row.debit - row.credit)
        elif row.account_type in _CREDIT_NATIVE:
            signed = money(row.credit - row.debit)
        else:
            raise ValueError(f"Unknown account type {row.account_type}")

        if row.account_type == "asset":
            assets += signed
        elif row.account_type == "liability":
            liabilities += signed
        elif row.account_type == "equity":
            equity += signed
        elif row.account_type == "income":
            income += signed
        elif row.account_type == "expense":
            expenses += signed

    rhs = money(liabilities + equity + income - expenses)
    delta = money(assets - rhs)
    return EquationSnapshot(
        as_of=as_of,
        assets=money(assets),
        liabilities=money(liabilities),
        equity=money(equity),
        income=money(income),
        expenses=money(expenses),
        delta=delta,
    )
