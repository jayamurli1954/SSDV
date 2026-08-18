from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.gl import AP_CONTROL, AR_CONTROL
from ssdv.models import JournalLine, Voucher
from ssdv.money import ZERO, money


def _party_net(
    session: Session,
    account_code: str,
    as_of: date,
    party_type: str,
) -> dict[str, Decimal]:
    stmt = (
        select(
            JournalLine.party_code,
            func.sum(JournalLine.debit),
            func.sum(JournalLine.credit),
        )
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(JournalLine.account_code == account_code)
        .where(JournalLine.party_type == party_type)
        .where(JournalLine.party_code.isnot(None))
        .where(Voucher.voucher_date <= as_of)
        .group_by(JournalLine.party_code)
    )
    out: dict[str, Decimal] = {}
    for code, debit, credit in session.execute(stmt):
        net = money(Decimal(debit or 0) - Decimal(credit or 0))
        if net != ZERO:
            out[str(code)] = net
    return out


def ar_subledger(session: Session, as_of: date) -> dict[str, Decimal]:
    """Customer-wise net debit on the AR control account."""
    return _party_net(session, AR_CONTROL, as_of, "customer")


def ap_subledger(session: Session, as_of: date) -> dict[str, Decimal]:
    """Vendor-wise net credit on the AP control account (stored as positive credit)."""
    raw = _party_net(session, AP_CONTROL, as_of, "vendor")
    return {code: money(-net) for code, net in raw.items() if net != ZERO}


def subledger_total(balances: dict[str, Decimal]) -> Decimal:
    return money(sum(balances.values(), ZERO))
