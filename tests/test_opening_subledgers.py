from datetime import date

from ssdv.accounting.opening import bootstrap_books
from ssdv.accounting.subledger import ap_subledger, ar_subledger, subledger_total
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.gl import AP_CONTROL, AR_CONTROL, INVENTORY
from ssdv.inventory.stock import stock_quantity, stock_value
from ssdv.money import ZERO, money
from ssdv.validate import run_gates


def test_opening_ar_ap_match_control_accounts(session) -> None:
    bootstrap_books(session)
    as_of = date(2023, 4, 1)
    ar = ar_subledger(session, as_of)
    ap = ap_subledger(session, as_of)
    assert subledger_total(ar) == money("8000000.00")
    assert subledger_total(ar) == ledger_balance(session, AR_CONTROL, as_of)
    assert subledger_total(ap) == money("6000000.00")
    assert subledger_total(ap) == money(-ledger_balance(session, AP_CONTROL, as_of))
    assert all(amount > ZERO for amount in ar.values())
    assert all(amount > ZERO for amount in ap.values())


def test_opening_stock_matches_inventory_gl(session) -> None:
    bootstrap_books(session)
    as_of = date(2023, 4, 1)
    assert stock_value(session, as_of) == money("12000000.00")
    assert stock_value(session, as_of) == ledger_balance(session, INVENTORY, as_of)
    assert stock_quantity(session, as_of) > ZERO


def test_validation_gates_pass_after_bootstrap(session) -> None:
    bootstrap_books(session)
    gates = run_gates(session, date(2023, 4, 1))
    failed = [g.name for g in gates if not g.ok]
    assert failed == []
