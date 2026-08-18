from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.accounting.posting import PostingError
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.cash.aging import aging_totals, ar_aging
from ssdv.cash.generate import generate_settlements
from ssdv.cash.posting import post_payment, post_receipt
from ssdv.gl import AP_CONTROL, AR_CONTROL, BANK_HDFC
from ssdv.inventory.stock import stock_quantity
from ssdv.models import Customer, Product, Vendor, Warehouse
from ssdv.money import money
from ssdv.purchases.generate import generate_purchases
from ssdv.purchases.posting import PurchaseLineInput, post_purchase
from ssdv.sales.generate import generate_sales
from ssdv.sales.posting import SalesLineInput, post_sale
from ssdv.validate import VOLUME_GATES, run_gates

SKIP_COUNTS = VOLUME_GATES


def _stocked_product(session, min_qty: Decimal = Decimal("10")) -> Product:
    as_of = date(2026, 3, 31)
    for product in session.scalars(select(Product).order_by(Product.code)):
        if stock_quantity(session, as_of, product.code) >= min_qty:
            return product
    raise AssertionError("No product with enough opening stock")


def _first(session, model, **filters):
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    item = session.scalars(stmt.limit(1)).first()
    assert item is not None
    return item


def test_receipt_reduces_ar_and_credits_bank(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session)
    warehouse = _first(session, Warehouse)
    customer = session.scalars(select(Customer).where(Customer.state_code == "27")).first()
    assert customer is not None
    invoice = post_sale(
        session,
        invoice_date=date(2023, 4, 3),
        customer=customer,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=Decimal("2"), rate=money(product.selling_price))],
    )
    as_of = date(2023, 4, 10)
    ar_before = ledger_balance(session, AR_CONTROL, as_of)
    bank_before = ledger_balance(session, BANK_HDFC, as_of)
    receipt = post_receipt(
        session,
        receipt_date=date(2023, 4, 10),
        customer=customer,
        bank_gl=BANK_HDFC,
        amount=invoice.grand_total,
        allocations=[(invoice.invoice_no, invoice.grand_total)],
    )
    assert receipt.amount == invoice.grand_total
    assert ledger_balance(session, AR_CONTROL, as_of) == money(ar_before - invoice.grand_total)
    assert ledger_balance(session, BANK_HDFC, as_of) == money(bank_before + invoice.grand_total)


def test_receipt_rejects_over_allocation(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session)
    warehouse = _first(session, Warehouse)
    customer = _first(session, Customer)
    invoice = post_sale(
        session,
        invoice_date=date(2023, 4, 3),
        customer=customer,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=Decimal("1"), rate=money(product.selling_price))],
    )
    post_receipt(
        session,
        receipt_date=date(2023, 4, 10),
        customer=customer,
        bank_gl=BANK_HDFC,
        amount=invoice.grand_total,
        allocations=[(invoice.invoice_no, invoice.grand_total)],
    )
    with pytest.raises(PostingError, match="Over-allocation"):
        post_receipt(
            session,
            receipt_date=date(2023, 4, 11),
            customer=customer,
            bank_gl=BANK_HDFC,
            amount=invoice.grand_total,
            allocations=[(invoice.invoice_no, invoice.grand_total)],
        )


def test_payment_reduces_ap(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session)
    warehouse = _first(session, Warehouse)
    vendor = session.scalars(select(Vendor).where(Vendor.state_code == "27")).first()
    assert vendor is not None
    bill = post_purchase(
        session,
        bill_date=date(2023, 4, 3),
        vendor=vendor,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal("10"), rate=money(product.cost_price))],
    )
    as_of = date(2023, 4, 10)
    ap_before = ledger_balance(session, AP_CONTROL, as_of)
    bank_before = ledger_balance(session, BANK_HDFC, as_of)
    payment = post_payment(
        session,
        payment_date=date(2023, 4, 10),
        vendor=vendor,
        bank_gl=BANK_HDFC,
        amount=bill.grand_total,
        allocations=[(bill.bill_no, bill.grand_total)],
    )
    assert payment.amount == bill.grand_total
    assert ledger_balance(session, AP_CONTROL, as_of) == money(ap_before + bill.grand_total)
    assert ledger_balance(session, BANK_HDFC, as_of) == money(bank_before - bill.grand_total)


def test_aging_sums_to_ar(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session)
    warehouse = _first(session, Warehouse)
    customer = _first(session, Customer)
    invoice = post_sale(
        session,
        invoice_date=date(2023, 4, 3),
        customer=customer,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=Decimal("2"), rate=money(product.selling_price))],
    )
    half = money(invoice.grand_total / Decimal("2"))
    post_receipt(
        session,
        receipt_date=date(2023, 4, 10),
        customer=customer,
        bank_gl=BANK_HDFC,
        amount=half,
        allocations=[(invoice.invoice_no, half)],
    )
    as_of = date(2023, 5, 15)
    ar_gl = ledger_balance(session, AR_CONTROL, as_of)
    totals = aging_totals(ar_aging(session, as_of))
    assert totals["total"] == ar_gl
    assert any(row.doc_ref == invoice.invoice_no for row in ar_aging(session, as_of))


def test_small_settlements_keep_books_tied(session) -> None:
    bootstrap_books(session)
    generate_purchases(session, target=12)
    generate_sales(session, target=8)
    created_r, created_p = generate_settlements(session, receipt_target=6, payment_target=4)
    assert created_r == 6
    assert created_p == 4
    assert generate_settlements(session, receipt_target=6, payment_target=4) == (0, 0)
    gates = run_gates(session, date(2026, 3, 31))
    failed = [g.name for g in gates if not g.ok and g.name not in SKIP_COUNTS]
    assert failed == []
