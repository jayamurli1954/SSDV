from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.accounting.posting import PostingError
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.cash.aging import aging_totals, ar_aging, bucket_for
from ssdv.cash.generate import generate_settlements
from ssdv.cash.parties import customer_vendor_tops
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


def test_aging_buckets_split_120() -> None:
    assert bucket_for(30) == "0-30"
    assert bucket_for(90) == "61-90"
    assert bucket_for(91) == "91-120"
    assert bucket_for(120) == "91-120"
    assert bucket_for(121) == "120+"


def _stocked_product(session, min_qty: Decimal = Decimal(10)) -> Product:
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
        lines=[SalesLineInput(product=product, qty=Decimal(2), rate=money(product.selling_price))],
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
        lines=[SalesLineInput(product=product, qty=Decimal(1), rate=money(product.selling_price))],
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
        lines=[PurchaseLineInput(product=product, qty=Decimal(10), rate=money(product.cost_price))],
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
        lines=[SalesLineInput(product=product, qty=Decimal(2), rate=money(product.selling_price))],
    )
    half = money(invoice.grand_total / Decimal(2))
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


def test_top_overdue_customers_rank_by_90_plus(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session, min_qty=Decimal(20))
    warehouse = _first(session, Warehouse)
    customers = list(session.scalars(select(Customer).order_by(Customer.code).limit(2)))
    vendors = list(session.scalars(select(Vendor).order_by(Vendor.code).limit(2)))
    assert len(customers) == 2
    assert len(vendors) == 2
    old_c, new_c = customers
    old_v, new_v = vendors
    old_inv = post_sale(
        session,
        invoice_date=date(2023, 4, 3),
        customer=old_c,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=Decimal(2), rate=money(product.selling_price))],
    )
    post_sale(
        session,
        invoice_date=date(2023, 7, 20),
        customer=new_c,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=Decimal(1), rate=money(product.selling_price))],
    )
    old_bill = post_purchase(
        session,
        bill_date=date(2023, 4, 3),
        vendor=old_v,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal(4), rate=money(product.cost_price))],
    )
    post_purchase(
        session,
        bill_date=date(2023, 7, 20),
        vendor=new_v,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal(2), rate=money(product.cost_price))],
    )
    as_of = date(2023, 8, 15)
    overdue, rank, exposure = customer_vendor_tops(session, as_of, limit=500)
    assert rank == "overdue_90"
    by_customer = {row.code: row for row in overdue}
    assert old_c.code in by_customer
    assert by_customer[old_c.code].name == old_c.name
    assert by_customer[old_c.code].overdue_90 >= old_inv.grand_total
    assert (by_customer[old_c.code].oldest_days or 0) >= 90
    by_vendor = {row.code: row for row in exposure}
    assert old_v.code in by_vendor
    assert by_vendor[old_v.code].outstanding >= old_bill.grand_total
    assert by_vendor[old_v.code].overdue_90 >= old_bill.grand_total


def test_overdue_rank_prefers_90_plus_over_larger_current_ar() -> None:
    from ssdv.cash.parties import PartyExposure, _top_overdue

    stale = PartyExposure(
        "C1", "Old Co", money("100"), money("80"), money("0"), 140, Decimal("0.40")
    )
    current = PartyExposure(
        "C2", "New Co", money("500"), money("0"), money("0"), 12, Decimal("0.60")
    )
    top, rank = _top_overdue([stale, current], 10)
    assert rank == "overdue_90"
    assert [row.code for row in top] == ["C1"]
    none, fallback = _top_overdue([current], 10)
    assert fallback == "outstanding"
    assert none[0].code == "C2"


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
