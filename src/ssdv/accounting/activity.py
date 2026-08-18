from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.models import JournalLine, Voucher
from ssdv.money import money


def voucher_account_net(
    session: Session,
    account_code: str,
    as_of: date,
    voucher_types: tuple[str, ...] | None = None,
    *,
    since: date | None = None,
    exclude_types: tuple[str, ...] | None = None,
) -> Decimal:
    """Net debit from matching voucher types through as_of.

    `since` is inclusive. `exclude_types` drops CLOSING (and similar) so a
    year-to-date P&L still reads after books are closed to equity.
    """
    stmt = (
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(JournalLine.account_code == account_code)
        .where(Voucher.voucher_date <= as_of)
    )
    if since is not None:
        stmt = stmt.where(Voucher.voucher_date >= since)
    if voucher_types:
        stmt = stmt.where(Voucher.voucher_type.in_(voucher_types))
    if exclude_types:
        stmt = stmt.where(Voucher.voucher_type.not_in(exclude_types))
    return money(session.scalar(stmt) or 0)
