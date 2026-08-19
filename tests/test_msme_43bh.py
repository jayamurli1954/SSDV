from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.forensics.msme_43bh import msme_43bh_risk
from ssdv.mis import mis_snapshot
from ssdv.models import Product, Vendor, Warehouse
from ssdv.money import money
from ssdv.paths import load_company
from ssdv.purchases.posting import PurchaseLineInput, post_purchase
from ssdv.scenarios import apply_scenario


def _cfg(name: str = "baseline") -> dict:
    return apply_scenario(load_company(), name)


def test_msme_43bh_risk_counts_only_overdue_msme_bills(session) -> None:
    cfg = _cfg()
    bootstrap_books(session, company=cfg)

    vendor = session.scalars(select(Vendor).order_by(Vendor.code)).first()
    warehouse = session.scalars(select(Warehouse).limit(1)).first()
    product = session.scalars(select(Product).limit(1)).first()
    assert vendor is not None and warehouse is not None and product is not None

    # Force the chosen vendor to be an MSME with agreement (43B(h) window = 45 days).
    vendor.msme_category = "Micro"
    vendor.msme_has_agreement = True
    session.flush()

    bill_date = date(2024, 1, 1)
    as_of = date(2024, 3, 1)  # 60 days after bill_date => overdue for 45 days

    bill = post_purchase(
        session,
        bill_date=bill_date,
        vendor=vendor,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal(1), rate=money(product.cost_price))],
        company=cfg,
    )

    total, top = msme_43bh_risk(session, as_of, limit=5)
    assert total == bill.grand_total
    assert len(top) >= 1
    assert top[0].vendor_code == vendor.code


def test_msme_43bh_total_is_wired_into_cfo_snapshot(session) -> None:
    cfg = _cfg()
    bootstrap_books(session, company=cfg)

    vendor = session.scalars(select(Vendor).order_by(Vendor.code)).first()
    warehouse = session.scalars(select(Warehouse).limit(1)).first()
    product = session.scalars(select(Product).limit(1)).first()
    assert vendor is not None and warehouse is not None and product is not None

    vendor.msme_category = "Small"
    vendor.msme_has_agreement = False
    session.flush()

    bill_date = date(2024, 1, 1)
    as_of = date(2024, 3, 20)  # 79 days => overdue for 15 days

    bill = post_purchase(
        session,
        bill_date=bill_date,
        vendor=vendor,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal(1), rate=money(product.cost_price))],
        company=cfg,
    )

    snap = mis_snapshot(session, as_of, company=cfg)
    assert snap.msme_43bh_total == bill.grand_total

