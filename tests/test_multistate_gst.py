from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.geo import HOME_STATE
from ssdv.inventory.stock import stock_quantity
from ssdv.models import Branch, Customer, Product, Vendor, Warehouse
from ssdv.money import money
from ssdv.purchases.posting import PurchaseLineInput, post_purchase
from ssdv.sales.posting import SalesLineInput, post_sale


def _pick_stocked_product(session, *, as_of: date, min_qty: Decimal = Decimal(1)) -> Product:
    for product in session.scalars(select(Product).order_by(Product.code)):
        if stock_quantity(session, as_of, product.code) >= min_qty:
            return product
    raise AssertionError("No stocked product found for the test")


def test_sales_post_sale_uses_warehouse_branch_state_for_interstate(session) -> None:
    bootstrap_books(session)
    as_of = date(2023, 4, 10)

    customer = session.scalars(
        select(Customer).where(Customer.state_code == HOME_STATE).order_by(Customer.code).limit(1)
    ).first()
    assert customer is not None

    product = _pick_stocked_product(session, as_of=as_of, min_qty=Decimal(1))

    # Create a warehouse in a different state from the customer.
    other_state = "29" if HOME_STATE != "29" else "24"
    branch = Branch(
        code="BR-MS-GST", name="Multi-state GST Branch", city="X", state_code=other_state
    )
    session.add(branch)
    session.flush()

    warehouse = Warehouse(
        code="WH-MS-GST",
        name="Multi-state GST Warehouse",
        branch_code=branch.code,
    )
    session.add(warehouse)
    session.flush()

    invoice = post_sale(
        session,
        invoice_date=as_of,
        customer=customer,
        warehouse=warehouse,
        lines=[SalesLineInput(product=product, qty=Decimal(1), rate=money(product.selling_price))],
    )
    assert invoice.interstate is True
    assert invoice.cgst == 0
    assert invoice.sgst == 0
    assert invoice.igst > 0


def test_purchase_post_purchase_uses_warehouse_branch_state_for_interstate(session) -> None:
    bootstrap_books(session)
    as_of = date(2023, 4, 10)

    vendor = session.scalars(
        select(Vendor).where(Vendor.state_code == HOME_STATE).order_by(Vendor.code).limit(1)
    ).first()
    assert vendor is not None

    product = _pick_stocked_product(session, as_of=as_of, min_qty=Decimal(1))

    # Create a warehouse in a different state from the vendor.
    other_state = "29" if HOME_STATE != "29" else "24"
    branch = Branch(
        code="BR-MS-GST-PUR", name="Multi-state GST Branch PUR", city="X", state_code=other_state
    )
    session.add(branch)
    session.flush()

    warehouse = Warehouse(
        code="WH-MS-GST-PUR",
        name="Multi-state GST Warehouse PUR",
        branch_code=branch.code,
    )
    session.add(warehouse)
    session.flush()

    bill = post_purchase(
        session,
        bill_date=as_of,
        vendor=vendor,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal(1), rate=money(product.cost_price))],
    )
    assert bill.interstate is True
    assert bill.cgst == 0
    assert bill.sgst == 0
    assert bill.igst > 0
