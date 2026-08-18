from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from ssdv.accounting.equation import accounting_equation
from ssdv.accounting.opening import bootstrap_books
from ssdv.accounting.posting import PostingError
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.banking.posting import post_bank_charge, post_emi
from ssdv.close.posting import post_closing, post_depreciation
from ssdv.expenses.posting import pay_opex, post_opex
from ssdv.gl import (
    ACCUM_DEP_FURNITURE,
    BANK_CHARGES,
    BANK_HDFC,
    DEPRECIATION,
    EXPENSES_PAYABLE,
    GST_PAYABLE,
    INPUT_CGST,
    INTEREST_LOAN,
    OUTPUT_CGST,
    PL_ACCOUNT,
    SALARIES,
    SALARY_PAYABLE,
    TERM_LOAN,
)
from ssdv.inventory.stock import stock_quantity
from ssdv.models import Customer, Product, Vendor, Warehouse
from ssdv.money import money
from ssdv.period import generate_books
from ssdv.purchases.posting import PurchaseLineInput, post_purchase
from ssdv.sales.posting import SalesLineInput, post_sale
from ssdv.tax.posting import post_gst_settlement
from ssdv.validate import VOLUME_GATES, run_gates


def _stocked_product(session, min_qty: Decimal = Decimal("10")) -> Product:
    as_of = date(2026, 3, 31)
    for product in session.scalars(select(Product).order_by(Product.code)):
        if stock_quantity(session, as_of, product.code) >= min_qty:
            return product
    raise AssertionError("No product with enough opening stock")


def test_opex_accrual_and_payment(session) -> None:
    bootstrap_books(session)
    as_of = date(2023, 4, 28)
    payable_before = ledger_balance(session, SALARY_PAYABLE, as_of)
    bank_before = ledger_balance(session, BANK_HDFC, as_of)
    entry = post_opex(
        session,
        expense_date=date(2023, 4, 28),
        kind="salary",
        account_code=SALARIES,
        amount=money("100000"),
        payable_gl=SALARY_PAYABLE,
    )
    assert ledger_balance(session, SALARIES, as_of) == money("100000")
    assert ledger_balance(session, SALARY_PAYABLE, as_of) == money(payable_before - money("100000"))
    pay_opex(session, entry, pay_date=as_of, bank_gl=BANK_HDFC, amount=money("100000"))
    assert ledger_balance(session, BANK_HDFC, as_of) == money(bank_before - money("100000"))
    with pytest.raises(PostingError, match="Over-payment"):
        pay_opex(session, entry, pay_date=as_of, bank_gl=BANK_HDFC, amount=money("1"))


def test_bank_charge_and_emi(session) -> None:
    bootstrap_books(session)
    as_of = date(2023, 4, 5)
    bank_before = ledger_balance(session, BANK_HDFC, as_of)
    loan_before = ledger_balance(session, TERM_LOAN, as_of)
    post_bank_charge(session, charge_date=as_of, bank_gl=BANK_HDFC, amount=money("1500"))
    assert ledger_balance(session, BANK_CHARGES, as_of) == money("1500")
    assert ledger_balance(session, BANK_HDFC, as_of) == money(bank_before - money("1500"))
    post_emi(
        session,
        emi_date=as_of,
        principal=money("60000"),
        interest=money("50000"),
        bank_gl=BANK_HDFC,
    )
    assert ledger_balance(session, INTEREST_LOAN, as_of) == money("50000")
    assert ledger_balance(session, TERM_LOAN, as_of) == money(loan_before + money("60000"))
    assert ledger_balance(session, BANK_HDFC, as_of) == money(bank_before - money("1500") - money("110000"))


def test_depreciation_and_year_end_close(session) -> None:
    bootstrap_books(session)
    fy_end = date(2024, 3, 31)
    dep = post_depreciation(session, fy_end)
    assert dep is not None
    assert ledger_balance(session, DEPRECIATION, fy_end) == money("100000")
    assert money(-ledger_balance(session, ACCUM_DEP_FURNITURE, fy_end)) == money("100000")
    close = post_closing(session, fy_end)
    assert close is not None
    assert post_depreciation(session, fy_end) is None
    assert post_closing(session, fy_end) is None
    snap = accounting_equation(session, fy_end)
    assert snap.holds
    assert snap.income == money("0")
    assert snap.expenses == money("0")
    assert ledger_balance(session, PL_ACCOUNT, fy_end) == money("100000")


def test_gst_setoff_and_payment(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session)
    warehouse = session.scalars(select(Warehouse).limit(1)).first()
    vendor = session.scalars(select(Vendor).where(Vendor.state_code == "27")).first()
    customer = session.scalars(select(Customer).where(Customer.state_code == "27")).first()
    assert warehouse is not None and vendor is not None and customer is not None
    bill = post_purchase(
        session,
        bill_date=date(2023, 4, 4),
        vendor=vendor,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal("4"), rate=money(product.cost_price))],
    )
    invoice = post_sale(
        session,
        invoice_date=date(2023, 4, 10),
        customer=customer,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=Decimal("2"), rate=money(product.selling_price))],
    )
    row = post_gst_settlement(
        session,
        period="2023-04",
        period_end=date(2023, 4, 30),
        settlement_date=date(2023, 5, 20),
        output_cgst=invoice.cgst,
        output_sgst=invoice.sgst,
        output_igst=invoice.igst,
        input_cgst=bill.cgst,
        input_sgst=bill.sgst,
        input_igst=bill.igst,
        paid=money("0"),
    )
    as_of = date(2023, 5, 20)
    assert row.itc_cgst == min(bill.cgst, invoice.cgst)
    assert ledger_balance(session, INPUT_CGST, as_of) == money(bill.cgst - row.itc_cgst)
    assert ledger_balance(session, OUTPUT_CGST, as_of) == money("0")
    assert money(-ledger_balance(session, GST_PAYABLE, as_of)) == row.payable


def test_generate_books_closes_years(session) -> None:
    bootstrap_books(session)
    summary = generate_books(session)
    assert summary.expenses > 0
    assert summary.emis == 36
    assert summary.depreciation == 3
    assert summary.closing == 3
    assert generate_books(session).expenses == 0
    snap = accounting_equation(session, date(2026, 3, 31))
    assert snap.holds
    assert snap.income == money("0")
    assert snap.expenses == money("0")
    gates = run_gates(session, date(2026, 3, 31))
    failed = [
        g.name
        for g in gates
        if not g.ok
        and g.name not in VOLUME_GATES - {"depreciation", "year_closed", "expense_months", "emi_count"}
    ]
    assert failed == []
