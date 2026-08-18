from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.models import Account, JournalLine, Voucher
from ssdv.money import ZERO, money


@dataclass(frozen=True)
class TrialBalanceRow:
    account_code: str
    account_name: str
    account_type: str
    subtype: str
    debit: Decimal
    credit: Decimal

    @property
    def net_debit(self) -> Decimal:
        return money(self.debit - self.credit)


def trial_balance(session: Session, as_of: date) -> list[TrialBalanceRow]:
    stmt = (
        select(
            Account.code,
            Account.name,
            Account.type,
            Account.subtype,
            JournalLine.debit,
            JournalLine.credit,
        )
        .join(JournalLine, JournalLine.account_code == Account.code)
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(Voucher.voucher_date <= as_of)
        .where(Account.postable.is_(True))
    )
    totals: dict[str, TrialBalanceRow] = {}
    for code, name, acc_type, subtype, debit, credit in session.execute(stmt):
        row = totals.get(code)
        debit_amt = money(debit)
        credit_amt = money(credit)
        if row is None:
            totals[code] = TrialBalanceRow(
                account_code=code,
                account_name=name,
                account_type=acc_type,
                subtype=subtype,
                debit=debit_amt,
                credit=credit_amt,
            )
        else:
            totals[code] = TrialBalanceRow(
                account_code=code,
                account_name=name,
                account_type=acc_type,
                subtype=subtype,
                debit=money(row.debit + debit_amt),
                credit=money(row.credit + credit_amt),
            )

    rows: list[TrialBalanceRow] = []
    for row in totals.values():
        net = money(row.debit - row.credit)
        if net == ZERO:
            continue
        if net > ZERO:
            rows.append(
                TrialBalanceRow(
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_type=row.account_type,
                    subtype=row.subtype,
                    debit=net,
                    credit=ZERO,
                )
            )
        else:
            rows.append(
                TrialBalanceRow(
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_type=row.account_type,
                    subtype=row.subtype,
                    debit=ZERO,
                    credit=money(-net),
                )
            )
    rows.sort(key=lambda r: r.account_code)
    return rows


def tb_totals(rows: list[TrialBalanceRow]) -> tuple[Decimal, Decimal]:
    debit = sum((r.debit for r in rows), ZERO)
    credit = sum((r.credit for r in rows), ZERO)
    return money(debit), money(credit)


def ledger_balance(session: Session, account_code: str, as_of: date) -> Decimal:
    """Signed balance: debit-positive for assets/expenses, credit-positive returned as negative."""
    stmt = (
        select(JournalLine.debit, JournalLine.credit)
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(JournalLine.account_code == account_code)
        .where(Voucher.voucher_date <= as_of)
    )
    debit = ZERO
    credit = ZERO
    for d, c in session.execute(stmt):
        debit += money(d)
        credit += money(c)
    return money(debit - credit)
