from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.gl import AP_CONTROL, INPUT_CGST, INPUT_IGST, INPUT_SGST, INVENTORY
from ssdv.inventory.stock import stock_value
from ssdv.models import JournalLine, Product, Vendor, Warehouse
from ssdv.money import money
from ssdv.purchases.generate import generate_purchases
from ssdv.purchases.posting import PurchaseLineInput, post_purchase
from ssdv.validate import VOLUME_GATES, run_gates


def _first(session, model, **filters):
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    item = session.scalars(stmt.limit(1)).first()
    assert item is not None
    return item


def test_purchase_intra_and_inter_state_gst(session) -> None:
    bootstrap_books(session)
    product = _first(session, Product)
    warehouse = _first(session, Warehouse)
    vendor_mh = session.scalars(select(Vendor).where(Vendor.state_code == "27")).first()
    vendor_out = session.scalars(select(Vendor).where(Vendor.state_code != "27")).first()
    assert vendor_mh is not None and vendor_out is not None

    qty = Decimal("10")
    rate = money(product.cost_price)
    line = PurchaseLineInput(product=product, qty=qty, rate=rate)
    inv_before = ledger_balance(session, INVENTORY, date(2026, 3, 31))
    ap_before = ledger_balance(session, AP_CONTROL, date(2026, 3, 31))
    stock_before = stock_value(session, date(2026, 3, 31))

    intra = post_purchase(
        session,
        bill_date=date(2023, 4, 3),
        vendor=vendor_mh,
        warehouse=warehouse,
        lines=[line],
    )
    inter = post_purchase(
        session,
        bill_date=date(2023, 4, 4),
        vendor=vendor_out,
        warehouse=warehouse,
        lines=[line],
    )

    assert intra.interstate is False
    assert intra.igst == money("0")
    assert intra.cgst > money("0") and intra.sgst > money("0")
    assert intra.grand_total == money(intra.taxable + intra.cgst + intra.sgst)

    assert inter.interstate is True
    assert inter.cgst == money("0") and inter.sgst == money("0")
    assert inter.igst > money("0")
    assert inter.grand_total == money(inter.taxable + inter.igst)

    intra_lines = {
        row.account_code: row
        for row in session.scalars(
            select(JournalLine).where(JournalLine.voucher_id == intra.voucher_id)
        )
    }
    assert INPUT_CGST in intra_lines and INPUT_SGST in intra_lines
    assert INPUT_IGST not in intra_lines
    assert intra_lines[AP_CONTROL].party_code == vendor_mh.code

    inter_lines = {
        row.account_code: row
        for row in session.scalars(
            select(JournalLine).where(JournalLine.voucher_id == inter.voucher_id)
        )
    }
    assert INPUT_IGST in inter_lines
    assert INPUT_CGST not in inter_lines and INPUT_SGST not in inter_lines

    as_of = date(2023, 4, 4)
    taxable = money(intra.taxable + inter.taxable)
    assert ledger_balance(session, INVENTORY, as_of) == money(inv_before + taxable)
    assert stock_value(session, as_of) == money(stock_before + taxable)
    assert ledger_balance(session, AP_CONTROL, as_of) == money(
        ap_before - intra.grand_total - inter.grand_total
    )


def test_small_purchase_run_keeps_books_tied(session) -> None:
    bootstrap_books(session)
    created = generate_purchases(session, target=12)
    assert created == 12
    assert generate_purchases(session, target=12) == 0
    gates = run_gates(session, date(2026, 3, 31))
    failed = [g.name for g in gates if not g.ok and g.name not in VOLUME_GATES]
    assert failed == []
    assert ledger_balance(session, INVENTORY, date(2026, 3, 31)) == stock_value(
        session, date(2026, 3, 31)
    )
