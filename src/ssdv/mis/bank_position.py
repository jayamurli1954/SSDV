"""Cash and bank position under the client's own bank names. Deterministic; read-only.

The standard chart has fixed bank slots (111000 / 112000 current, 113000 overdraft,
110000 cash). A client's SBI, Axis or Kotak ledgers are classified into those slots,
so reports must show the client's own ledger names and balances, never the slot name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.gl import BANK_HDFC, BANK_ICICI, BANK_OD, CASH
from ssdv.models import Account, ClientLedger, JournalLine, Voucher
from ssdv.money import ZERO, money
from ssdv.paths import load_yaml

BANK_SLOTS = (BANK_HDFC, BANK_ICICI, BANK_OD)
CASH_SLOTS = (CASH, *BANK_SLOTS)


@dataclass(frozen=True)
class BankPosition:
    label: str
    standard_code: str
    balance: Decimal
    client_code: str | None = None

    @property
    def is_overdraft(self) -> bool:
        return self.standard_code == BANK_OD


def bank_positions(session: Session, as_of: date, *, imported: bool) -> tuple[BankPosition, ...]:
    """One row per bank / cash ledger. Imported books use the client's own ledgers;
    generated books (and lines from before client ledgers were kept) use the standard name."""
    slots = CASH_SLOTS if imported else BANK_SLOTS
    stmt = (
        select(
            ClientLedger.code,
            ClientLedger.name,
            Account.code,
            Account.name,
            func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0),
        )
        .select_from(JournalLine)
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .join(Account, Account.code == JournalLine.account_code)
        .outerjoin(ClientLedger, ClientLedger.id == JournalLine.client_ledger_id)
        .where(Voucher.voucher_date <= as_of)
        .where(JournalLine.account_code.in_(slots))
        .group_by(
            JournalLine.client_ledger_id,
            ClientLedger.code,
            ClientLedger.name,
            Account.code,
            Account.name,
        )
    )
    rows: list[BankPosition] = []
    for client_code, client_name, std_code, std_name, net in session.execute(stmt):
        label = str(client_name) if client_name else (
            str(std_name) if not imported else f"{std_name} (standard)"
        )
        rows.append(
            BankPosition(
                label=label,
                standard_code=str(std_code),
                balance=money(net),
                client_code=client_code,
            )
        )
    order = {code: i for i, code in enumerate(CASH_SLOTS)}
    return tuple(sorted(rows, key=lambda r: (order[r.standard_code], r.label.casefold())))


def vault_path(session: Session) -> Path | None:
    database = getattr(session.get_bind().url, "database", None)
    return Path(database) if database and database != ":memory:" else None


def client_od_limit(session: Session) -> Decimal:
    """Sanctioned overdraft limit for an imported client, from ``od_limit`` in the
    ``<vault-stem>.budget.yaml`` sidecar. Zero when not set: never borrowed from the
    sample company."""
    db = vault_path(session)
    if db is None:
        return ZERO
    for suffix in (".budget.yaml", ".budget.yml"):
        path = db.with_name(f"{db.stem}{suffix}")
        if path.is_file():
            raw = load_yaml(path).get("od_limit")
            return money(str(raw)) if raw is not None else ZERO
    return ZERO
