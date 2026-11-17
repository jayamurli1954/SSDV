"""Reports in the client's own chart of accounts. Deterministic; read-only.

Every imported journal line remembers the client ledger it came from (``ClientLedger``).
This module rolls the posted books back up by those ledgers, so a client sees their
own codes (1001 / 10001 / 100001), names and groups, alongside the standard ledger
OfficeMitra classified each one under. Books are never changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.fy import fy_start
from ssdv.models import Account, AccountType, ClientLedger, JournalLine, Voucher, VoucherType
from ssdv.money import ZERO, money

NO_GROUP = "(no group)"


@dataclass(frozen=True)
class ClientRow:
    client_code: str | None
    client_name: str
    client_group: str | None
    standard_code: str
    standard_name: str
    standard_type: str
    debit: Decimal
    credit: Decimal

    @property
    def balance(self) -> Decimal:
        """Debit-positive closing balance."""
        return money(self.debit - self.credit)


def has_client_chart(session: Session) -> bool:
    return bool(session.scalar(select(func.count()).select_from(ClientLedger)))


def _natural(code: str | None) -> tuple[int, int, str]:
    if not code:
        return (2, 0, "")
    if code.isdigit():
        return (0, int(code), code)
    return (1, 0, code.casefold())


def _rows(session: Session, *, start: date | None, end: date, pnl_only: bool) -> list[ClientRow]:
    stmt = (
        select(
            ClientLedger.code,
            ClientLedger.name,
            ClientLedger.group_name,
            Account.code,
            Account.name,
            Account.type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .select_from(JournalLine)
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .join(Account, Account.code == JournalLine.account_code)
        .outerjoin(ClientLedger, ClientLedger.id == JournalLine.client_ledger_id)
        .where(Voucher.voucher_date <= end)
        .group_by(
            JournalLine.client_ledger_id,
            ClientLedger.code,
            ClientLedger.name,
            ClientLedger.group_name,
            Account.code,
            Account.name,
            Account.type,
        )
    )
    if start is not None:
        stmt = stmt.where(Voucher.voucher_date >= start)
    if pnl_only:
        stmt = stmt.where(
            Account.type.in_((AccountType.INCOME.value, AccountType.EXPENSE.value))
        ).where(Voucher.voucher_type != VoucherType.CLOSING.value)
    out: list[ClientRow] = []
    for code, name, group, std_code, std_name, std_type, debit, credit in session.execute(stmt):
        out.append(
            ClientRow(
                client_code=code,
                # Lines from before client ledgers were tracked fall back to the standard ledger.
                client_name=str(name) if name else f"{std_name} (standard)",
                client_group=group,
                standard_code=str(std_code),
                standard_name=str(std_name),
                standard_type=str(std_type),
                debit=money(debit),
                credit=money(credit),
            )
        )
    return sorted(out, key=lambda r: (_natural(r.client_code), r.client_name.casefold()))


def client_trial_balance(session: Session, as_of: date) -> list[ClientRow]:
    """Every ledger in the client's chart with posted debits and credits to ``as_of``."""
    return [r for r in _rows(session, start=None, end=as_of, pnl_only=False) if r.balance != ZERO]


def client_pnl(session: Session, as_of: date) -> list[dict[str, Any]]:
    """Income and expense for the financial year to date, subtotalled by the client's groups."""
    groups: dict[tuple[str, str], list[ClientRow]] = {}
    for row in _rows(session, start=fy_start(as_of), end=as_of, pnl_only=True):
        key = (row.standard_type, row.client_group or NO_GROUP)
        groups.setdefault(key, []).append(row)
    out: list[dict[str, Any]] = []
    for kind in (AccountType.INCOME.value, AccountType.EXPENSE.value):
        for (row_kind, group), rows in sorted(groups.items(), key=lambda item: item[0][1].casefold()):
            if row_kind != kind:
                continue
            ledgers = []
            for row in rows:
                amount = money(row.credit - row.debit) if kind == "income" else row.balance
                if amount != ZERO:
                    ledgers.append(
                        {
                            "client_code": row.client_code,
                            "client_name": row.client_name,
                            "standard_code": row.standard_code,
                            "amount": str(amount),
                        }
                    )
            if ledgers:
                total = money(sum((Decimal(item["amount"]) for item in ledgers), ZERO))
                out.append({"type": kind, "group": group, "total": str(total), "ledgers": ledgers})
    return out


def client_chart_payload(session: Session, as_of: date) -> dict[str, Any] | None:
    if not has_client_chart(session):
        return None
    tb = client_trial_balance(session, as_of)
    return {
        "as_of": as_of.isoformat(),
        "trial_balance": [
            {
                "client_code": row.client_code,
                "client_name": row.client_name,
                "client_group": row.client_group,
                "standard_code": row.standard_code,
                "standard_name": row.standard_name,
                "debit": str(row.debit),
                "credit": str(row.credit),
                "balance": str(row.balance),
            }
            for row in tb
        ],
        "tb_total_debit": str(money(sum((r.debit for r in tb), ZERO))),
        "tb_total_credit": str(money(sum((r.credit for r in tb), ZERO))),
        "pnl": client_pnl(session, as_of),
    }
