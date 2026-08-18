from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.fy import iter_month_ends, month_key, month_label
from ssdv.gl import AP_CONTROL, AR_CONTROL, COGS, INVENTORY, SALES
from ssdv.models import Account, JournalLine, Voucher, VoucherType
from ssdv.money import ZERO, money


@dataclass(frozen=True)
class MonthlySeries:
    """Activity by calendar month from posted journals. Aligned arrays for charts."""

    grain: str
    start: date
    end: date
    categories: tuple[str, ...]
    labels: tuple[str, ...]
    sales: tuple[Decimal, ...]
    cogs: tuple[Decimal, ...]
    gross_margin: tuple[Decimal, ...]
    purchases: tuple[Decimal, ...]
    receipts: tuple[Decimal, ...]
    payments: tuple[Decimal, ...]
    opex: tuple[Decimal, ...]


def _empty(start: date, end: date) -> MonthlySeries:
    return MonthlySeries(
        grain="month",
        start=start,
        end=end,
        categories=(),
        labels=(),
        sales=(),
        cogs=(),
        gross_margin=(),
        purchases=(),
        receipts=(),
        payments=(),
        opex=(),
    )


def _align(categories: tuple[str, ...], buckets: dict[str, Decimal]) -> tuple[Decimal, ...]:
    return tuple(money(buckets.get(key, ZERO)) for key in categories)


def _bucket_dates(rows: list[tuple[date, Decimal]]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for voucher_date, raw in rows:
        key = month_key(voucher_date)
        out[key] = money(out.get(key, ZERO) + money(raw or 0))
    return out


def _account_by_month(
    session: Session,
    account_code: str,
    start: date,
    end: date,
    voucher_types: tuple[str, ...],
    *,
    negate: bool = False,
) -> dict[str, Decimal]:
    net = func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)
    stmt = (
        select(Voucher.voucher_date, net)
        .select_from(Voucher)
        .join(JournalLine, JournalLine.voucher_id == Voucher.id)
        .where(JournalLine.account_code == account_code)
        .where(Voucher.voucher_date >= start)
        .where(Voucher.voucher_date <= end)
        .where(Voucher.voucher_type.in_(voucher_types))
        .group_by(Voucher.voucher_date)
    )
    buckets = _bucket_dates([(row[0], money(row[1])) for row in session.execute(stmt)])
    if negate:
        return {key: money(-value) for key, value in buckets.items()}
    return buckets


def _opex_by_month(session: Session, start: date, end: date) -> dict[str, Decimal]:
    net = func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)
    stmt = (
        select(Voucher.voucher_date, net)
        .select_from(Voucher)
        .join(JournalLine, JournalLine.voucher_id == Voucher.id)
        .join(Account, Account.code == JournalLine.account_code)
        .where(Account.type == "expense")
        .where(Account.code != COGS)
        .where(Voucher.voucher_date >= start)
        .where(Voucher.voucher_date <= end)
        .where(Voucher.voucher_type != VoucherType.CLOSING.value)
        .group_by(Voucher.voucher_date)
    )
    return _bucket_dates([(row[0], money(row[1])) for row in session.execute(stmt)])


def monthly_activity(session: Session, start: date, end: date) -> MonthlySeries:
    """One point per month from books_start through as_of.

    The last month is partial when as_of is not month-end.
    """
    if end < start:
        return _empty(start, end)
    ends = iter_month_ends(start, end)
    categories = tuple(month_key(item) for item in ends)
    labels = tuple(month_label(item) for item in ends)
    sales = _align(
        categories,
        _account_by_month(session, SALES, start, end, (VoucherType.SALE.value,), negate=True),
    )
    cogs = _align(
        categories,
        _account_by_month(session, COGS, start, end, (VoucherType.SALE.value,)),
    )
    purchases = _align(
        categories,
        _account_by_month(session, INVENTORY, start, end, (VoucherType.PURCHASE.value,)),
    )
    receipts = _align(
        categories,
        _account_by_month(session, AR_CONTROL, start, end, (VoucherType.RECEIPT.value,), negate=True),
    )
    payments = _align(
        categories,
        _account_by_month(session, AP_CONTROL, start, end, (VoucherType.PAYMENT.value,)),
    )
    opex = _align(categories, _opex_by_month(session, start, end))
    gross = tuple(money(sale - cost) for sale, cost in zip(sales, cogs, strict=True))
    return MonthlySeries(
        grain="month",
        start=start,
        end=end,
        categories=categories,
        labels=labels,
        sales=sales,
        cogs=cogs,
        gross_margin=gross,
        purchases=purchases,
        receipts=receipts,
        payments=payments,
        opex=opex,
    )
