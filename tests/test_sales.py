from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.accounting.posting import PostingError
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.gl import AR_CONTROL, COGS, INVENTORY, OUTPUT_CGST, OUTPUT_IGST, OUTPUT_SGST, SALES
from ssdv.inventory.stock import stock_quantity, stock_value
from ssdv.models import Customer, JournalLine, Product, Warehouse
from ssdv.money import money
from ssdv.purchases.generate import generate_purchases
from ssdv.sales.generate import generate_sales
from ssdv.sales.posting import SalesLineInput, post_sale
from ssdv.validate import VOLUME_GATES, run_gates


def _stocked_product(session, min_qty: Decimal = Decimal(10)) -> Product:
    as_of = date(2026, 3, 31)
    for product in session.scalars(select(Product).order_by(Product.code)):
        if stock_quantity(session, as_of, product.code) >= min_qty:
            return product
    raise AssertionError("No product with enough opening stock")


def test_sale_intra_inter_and_cogs_at_wac(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session)
    warehouse = session.scalars(select(Warehouse).limit(1)).first()
    assert warehouse is not None
    customer_mh = session.scalars(select(Customer).where(Customer.state_code == "27")).first()
    customer_out = session.scalars(select(Customer).where(Customer.state_code != "27")).first()
    assert customer_mh is not None and customer_out is not None

    qty = Decimal(5)
    as_of_before = date(2023, 4, 1)
    wac = money(
        stock_value(session, as_of_before, product.code)
        / stock_quantity(session, as_of_before, product.code)
    )
    inv_before = ledger_balance(session, INVENTORY, date(2023, 4, 5))
    stock_before = stock_value(session, date(2023, 4, 5))
    ar_before = ledger_balance(session, AR_CONTROL, date(2023, 4, 5))

    intra = post_sale(
        session,
        invoice_date=date(2023, 4, 3),
        customer=customer_mh,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=qty, rate=money(product.selling_price))],
    )
    inter = post_sale(
        session,
        invoice_date=date(2023, 4, 4),
        customer=customer_out,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=qty, rate=money(product.selling_price))],
    )

    assert intra.interstate is False
    assert intra.igst == money("0")
    assert intra.cgst > money("0") and intra.sgst > money("0")
    assert intra.cogs > money("0")
    assert intra.cogs != intra.taxable
    assert intra.lines[0].cogs_rate == wac

    assert inter.interstate is True
    assert inter.igst > money("0")
    assert inter.cgst == money("0") and inter.sgst == money("0")

    intra_accounts = {
        row.account_code
        for row in session.scalars(
            select(JournalLine).where(JournalLine.voucher_id == intra.voucher_id)
        )
    }
    assert {SALES, COGS, INVENTORY, AR_CONTROL, OUTPUT_CGST, OUTPUT_SGST} <= intra_accounts
    assert OUTPUT_IGST not in intra_accounts

    inter_accounts = {
        row.account_code
        for row in session.scalars(
            select(JournalLine).where(JournalLine.voucher_id == inter.voucher_id)
        )
    }
    assert OUTPUT_IGST in inter_accounts
    assert OUTPUT_CGST not in inter_accounts

    as_of = date(2023, 4, 4)
    cogs = money(intra.cogs + inter.cogs)
    assert ledger_balance(session, INVENTORY, as_of) == money(inv_before - cogs)
    assert stock_value(session, as_of) == money(stock_before - cogs)
    assert ledger_balance(session, AR_CONTROL, as_of) == money(
        ar_before + intra.grand_total + inter.grand_total
    )
    assert ledger_balance(session, SALES, as_of) == money(-(intra.taxable + inter.taxable))
    assert ledger_balance(session, COGS, as_of) == cogs


def test_sale_rejects_negative_stock(session) -> None:
    bootstrap_books(session)
    product = _stocked_product(session, min_qty=Decimal(1))
    warehouse = session.scalars(select(Warehouse).limit(1)).first()
    customer = session.scalars(select(Customer).limit(1)).first()
    assert warehouse is not None and customer is not None
    available = stock_quantity(session, date(2023, 4, 3), product.code)
    with pytest.raises(PostingError, match="Insufficient stock"):
        post_sale(
            session,
            invoice_date=date(2023, 4, 3),
            customer=customer,
            warehouse=warehouse,
            lines=[
                SalesLineInput(
                    product=product,
                    qty=available + Decimal(1),
                    rate=money(product.selling_price),
                )
            ],
        )


def test_small_sales_run_keeps_books_tied(session) -> None:
    bootstrap_books(session)
    generate_purchases(session, target=12)
    created = generate_sales(session, target=8)
    assert created == 8
    assert generate_sales(session, target=8) == 0
    gates = run_gates(session, date(2026, 3, 31))
    failed = [g.name for g in gates if not g.ok and g.name not in VOLUME_GATES]
    assert failed == []
    assert ledger_balance(session, INVENTORY, date(2026, 3, 31)) == stock_value(
        session, date(2026, 3, 31)
    )
    assert stock_quantity(session, date(2026, 3, 31)) >= 0
