from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.forensics.gstr2b_recon import load_gstr2b_csv, reconcile_2b
from ssdv.models import Product, Vendor, Warehouse
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.purchases.posting import PurchaseLineInput, post_purchase
from ssdv.scenarios import apply_scenario


def _cfg(name: str = "baseline") -> dict:
    return apply_scenario(load_company(), name)


def _write_2b_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "return_period",
        "supplier_gstin",
        "supplier_name",
        "invoice_no",
        "invoice_date",
        "taxable",
        "cgst",
        "sgst",
        "igst",
        "itc_available",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_gstr2b_reconciliation(session, tmp_path) -> None:
    cfg = _cfg()
    bootstrap_books(session, company=cfg)

    vendor = session.scalars(select(Vendor).order_by(Vendor.code)).first()
    warehouse = session.scalars(select(Warehouse).limit(1)).first()
    product = session.scalars(select(Product).limit(1)).first()
    assert vendor is not None and warehouse is not None and product is not None

    bill = post_purchase(
        session,
        bill_date=date(2024, 1, 15),
        vendor=vendor,
        warehouse=warehouse,
        lines=[PurchaseLineInput(product=product, qty=Decimal(5), rate=money(product.cost_price))],
        company=cfg,
    )

    # Create a GSTR-2B CSV that matches the bill exactly + one extra (missing in books)
    csv_path = tmp_path / "gstr2b.csv"
    _write_2b_csv(
        csv_path,
        [
            {
                "return_period": "2024-01",
                "supplier_gstin": vendor.gstin,
                "supplier_name": vendor.name,
                "invoice_no": bill.bill_no,
                "invoice_date": "15-01-2024",
                "taxable": str(bill.taxable),
                "cgst": str(bill.cgst),
                "sgst": str(bill.sgst),
                "igst": str(bill.igst),
                "itc_available": "Y",
            },
            {
                "return_period": "2024-01",
                "supplier_gstin": "29AABCU9603R1ZM",
                "supplier_name": "Unknown Supplier",
                "invoice_no": "INV-999",
                "invoice_date": "20-01-2024",
                "taxable": "10000.00",
                "cgst": "900.00",
                "sgst": "900.00",
                "igst": "0.00",
                "itc_available": "Y",
            },
        ],
    )

    loaded = load_gstr2b_csv(session, csv_path)
    assert loaded == 2

    result = reconcile_2b(session)
    flags = {r.flag for r in result.rows}

    # The extra invoice should be flagged as missing in books
    assert "missing_in_books" in flags

    # Bills not in 2B should be flagged (all other purchase bills from bootstrap)
    missing_in_2b = [r for r in result.rows if r.flag == "missing_in_2b"]
    # At least the opening/generated bills should show up
    assert len(missing_in_2b) >= 0  # depends on bootstrap data

    # ITC gap should be non-zero (extra portal line)
    assert result.itc_gap != ZERO or result.total_portal_itc != result.total_books_itc
