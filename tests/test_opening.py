from datetime import date

from ssdv.accounting.equation import accounting_equation
from ssdv.accounting.opening import bootstrap_books, post_opening
from ssdv.accounting.trial_balance import tb_totals, trial_balance
from ssdv.money import money


def test_opening_trial_balance_ties(session) -> None:
    bootstrap_books(session)
    rows = trial_balance(session, date(2023, 4, 1))
    debit, credit = tb_totals(rows)
    assert debit == credit
    assert debit == money("28000000.00")


def test_opening_accounting_equation_holds(session) -> None:
    bootstrap_books(session)
    snap = accounting_equation(session, date(2023, 4, 1))
    assert snap.holds
    assert snap.assets == money("28000000.00")
    assert snap.liabilities == money("11000000.00")
    assert snap.equity == money("17000000.00")
    assert snap.income == money("0")
    assert snap.expenses == money("0")


def test_opening_is_idempotent(session) -> None:
    first = bootstrap_books(session)
    second = post_opening(session)
    assert second is not None
    assert first.id == second.id
    rows = trial_balance(session, date(2023, 4, 1))
    debit, credit = tb_totals(rows)
    assert debit == money("28000000.00")
    assert debit == credit


def test_empty_tb_before_opening(session) -> None:
    rows = trial_balance(session, date(2023, 4, 1))
    assert rows == []
    snap = accounting_equation(session, date(2023, 4, 1))
    assert snap.holds
    assert snap.assets == money("0")
