"""Account-level budget vs actual and the top variance drivers. Deterministic; no LLM math.

Budgets come from the optional ``<vault-stem>.budget.yaml`` sidecar (``accounts:``).
Actuals are the posted income and expense ledgers for the financial year to the as-of
date. Books are never changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.fy import fy_code, fy_end, fy_start
from ssdv.models import Account, AccountType, JournalLine, Voucher, VoucherType
from ssdv.money import ZERO, money
from ssdv.paths import load_yaml

BASIS_ANNUAL = "annual"
BASIS_TO_DATE = "to_date"
TOP_DRIVERS = 5
BUDGET_METHOD = (
    "Actuals are posted income and expense ledgers for the financial year to the as-of "
    "date. Annual budgets are pro-rated by days elapsed in the financial year. "
    "Variance is actual minus budget; profit impact is positive when it helps profit."
)


@dataclass(frozen=True)
class AccountBudget:
    basis: str
    amounts: dict[str, Decimal]


@dataclass(frozen=True)
class AccountActual:
    code: str
    name: str
    type: str
    amount: Decimal


@dataclass(frozen=True)
class VarianceRow:
    code: str
    name: str
    type: str
    actual: Decimal
    budget: Decimal
    variance: Decimal
    variance_pct: Decimal | None
    profit_impact: Decimal

    @property
    def favourable(self) -> bool:
        return self.profit_impact >= ZERO


@dataclass(frozen=True)
class BudgetReport:
    fy_code: str
    basis: str
    elapsed_pct: Decimal
    rows: tuple[VarianceRow, ...]
    unmatched: tuple[str, ...]
    unbudgeted_expense: Decimal
    unbudgeted_count: int

    @property
    def profit_impact(self) -> Decimal:
        return money(sum((row.profit_impact for row in self.rows), ZERO))

    @property
    def drivers(self) -> tuple[VarianceRow, ...]:
        moved = [row for row in self.rows if row.profit_impact != ZERO]
        ranked = sorted(moved, key=lambda row: (-abs(row.profit_impact), row.code))
        return tuple(ranked[:TOP_DRIVERS])


def _budget_file(db_path: Path) -> Path | None:
    for suffix in (".budget.yaml", ".budget.yml"):
        path = db_path.with_name(f"{db_path.stem}{suffix}")
        if path.is_file():
            return path
    return None


def load_account_budget(db_path: Path, *, fy: str) -> AccountBudget | None:
    """Read ``accounts:`` from the sidecar. A map keyed by FY code picks that year."""
    path = _budget_file(db_path)
    if path is None:
        return None
    raw = load_yaml(path)
    accounts = raw.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        return None
    if all(isinstance(value, dict) for value in accounts.values()):
        accounts = accounts.get(fy)
        if not isinstance(accounts, dict) or not accounts:
            return None
    basis = str(raw.get("budget_basis") or BASIS_ANNUAL).strip().lower()
    if basis not in {BASIS_ANNUAL, BASIS_TO_DATE}:
        raise ValueError(
            f"budget_basis in {path.name} must be '{BASIS_ANNUAL}' or '{BASIS_TO_DATE}', not {basis!r}"
        )
    amounts = {str(key).strip(): money(str(value)) for key, value in accounts.items()}
    return AccountBudget(basis=basis, amounts=amounts)


def account_actuals(session: Session, start: date, end: date) -> list[AccountActual]:
    """Income (credit - debit) and expense (debit - credit) per ledger, closing entries excluded."""
    stmt = (
        select(
            Account.code,
            Account.name,
            Account.type,
            func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_code == Account.code)
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(Account.type.in_((AccountType.INCOME.value, AccountType.EXPENSE.value)))
        .where(Voucher.voucher_date >= start)
        .where(Voucher.voucher_date <= end)
        .where(Voucher.voucher_type != VoucherType.CLOSING.value)
        .group_by(Account.code, Account.name, Account.type)
        .order_by(Account.code)
    )
    out: list[AccountActual] = []
    for code, name, kind, net_debit in session.execute(stmt):
        net = money(net_debit)
        amount = money(-net) if kind == AccountType.INCOME.value else net
        out.append(AccountActual(code=str(code), name=str(name), type=str(kind), amount=amount))
    return out


def pnl_accounts(session: Session) -> list[AccountActual]:
    stmt = (
        select(Account.code, Account.name, Account.type)
        .where(Account.type.in_((AccountType.INCOME.value, AccountType.EXPENSE.value)))
        .where(Account.postable.is_(True))
    )
    return [
        AccountActual(code=str(code), name=str(name), type=str(kind), amount=ZERO)
        for code, name, kind in session.execute(stmt)
    ]


def elapsed_fraction(as_of: date) -> Decimal:
    start, end = fy_start(as_of), fy_end(as_of)
    return Decimal((as_of - start).days + 1) / Decimal((end - start).days + 1)


def build_variance(
    *,
    budget: AccountBudget,
    actuals: list[AccountActual],
    chart: list[AccountActual],
    as_of: date,
) -> BudgetReport:
    """Pure: pair each budgeted ledger with its posted actual and rank the drivers."""
    known = {item.code: item for item in chart}
    known.update({item.code: item for item in actuals})
    by_name = {item.name.casefold(): item for item in known.values()}
    posted = {item.code: item.amount for item in actuals}
    fraction = elapsed_fraction(as_of) if budget.basis == BASIS_ANNUAL else Decimal(1)

    budgeted: dict[str, Decimal] = {}
    unmatched: list[str] = []
    for key, amount in budget.amounts.items():
        account = known.get(key) or by_name.get(key.casefold())
        if account is None:
            unmatched.append(key)
            continue
        budgeted[account.code] = money(budgeted.get(account.code, ZERO) + amount * fraction)

    rows: list[VarianceRow] = []
    for code in sorted(budgeted):
        account = known[code]
        actual = money(posted.get(code, ZERO))
        target = budgeted[code]
        variance = money(actual - target)
        is_income = account.type == AccountType.INCOME.value
        rows.append(
            VarianceRow(
                code=code,
                name=account.name,
                type=account.type,
                actual=actual,
                budget=target,
                variance=variance,
                variance_pct=None if target == ZERO else (variance / target).quantize(Decimal("0.0001")),
                profit_impact=variance if is_income else money(-variance),
            )
        )

    stray = [
        item
        for item in actuals
        if item.type == AccountType.EXPENSE.value
        and item.code not in budgeted
        and item.amount != ZERO
    ]
    return BudgetReport(
        fy_code=fy_code(as_of),
        basis=budget.basis,
        elapsed_pct=fraction.quantize(Decimal("0.0001")),
        rows=tuple(rows),
        unmatched=tuple(unmatched),
        unbudgeted_expense=money(sum((item.amount for item in stray), ZERO)),
        unbudgeted_count=len(stray),
    )


def budget_report(session: Session, db_path: Path, as_of: date) -> BudgetReport | None:
    budget = load_account_budget(db_path, fy=fy_code(as_of))
    if budget is None:
        return None
    return build_variance(
        budget=budget,
        actuals=account_actuals(session, fy_start(as_of), as_of),
        chart=pnl_accounts(session),
        as_of=as_of,
    )


def _row_dict(row: VarianceRow) -> dict[str, Any]:
    return {
        "code": row.code,
        "name": row.name,
        "type": row.type,
        "actual": str(row.actual),
        "budget": str(row.budget),
        "variance": str(row.variance),
        "variance_pct": None if row.variance_pct is None else str(row.variance_pct),
        "profit_impact": str(row.profit_impact),
        "favourable": row.favourable,
    }


def report_as_dict(report: BudgetReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "fy_code": report.fy_code,
        "basis": report.basis,
        "elapsed_pct": str(report.elapsed_pct),
        "method": BUDGET_METHOD,
        "profit_impact": str(report.profit_impact),
        "rows": [_row_dict(row) for row in report.rows],
        "drivers": [_row_dict(row) for row in report.drivers],
        "unmatched": list(report.unmatched),
        "unbudgeted_expense": str(report.unbudgeted_expense),
        "unbudgeted_count": report.unbudgeted_count,
    }
