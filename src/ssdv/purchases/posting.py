from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingRequest, post
from ssdv.fy import fy_code
from ssdv.gl import AP_CONTROL, INPUT_CGST, INPUT_IGST, INPUT_SGST, INVENTORY
from ssdv.gst import gst_split, is_interstate
from ssdv.inventory.stock import record_stock_move
from ssdv.models import (
    Product,
    PurchaseBill,
    PurchaseBillLine,
    Vendor,
    VoucherType,
    Warehouse,
)
from ssdv.money import ZERO, money
from ssdv.paths import load_company


@dataclass(frozen=True)
class PurchaseLineInput:
    product: Product
    qty: Decimal
    rate: Decimal


def _next_doc_no(session: Session, fy: str) -> int:
    count = session.scalar(
        select(func.count()).select_from(PurchaseBill).where(PurchaseBill.fy_code == fy)
    )
    return int(count or 0) + 1


def post_purchase(
    session: Session,
    *,
    bill_date: date,
    vendor: Vendor,
    warehouse: Warehouse,
    lines: list[PurchaseLineInput],
    company: dict | None = None,
    scenario: str | None = None,
) -> PurchaseBill:
    if not lines:
        raise ValueError("A purchase bill needs at least one line")

    cfg = company or load_company()
    home_state = str(cfg["accounting"]["home_state_code"])
    if vendor.state_code is None:
        raise ValueError(f"Vendor {vendor.code} has no state")
    interstate = is_interstate(vendor.state_code, home_state)
    fy = fy_code(bill_date)
    seq = _next_doc_no(session, fy)
    bill_no = f"PUR/{fy}/{seq:06d}"
    grn_no = f"GRN/{fy}/{seq:06d}"

    drafted: list[tuple[PurchaseLineInput, Decimal, Decimal, Decimal, Decimal]] = []
    taxable = ZERO
    tot_cgst = ZERO
    tot_sgst = ZERO
    tot_igst = ZERO
    for raw in lines:
        if raw.qty <= ZERO or raw.rate <= ZERO:
            raise ValueError(f"Invalid qty/rate for {raw.product.code}")
        amount = money(raw.qty * raw.rate)
        cgst, sgst, igst = gst_split(amount, money(raw.product.gst_rate), interstate)
        drafted.append((raw, amount, cgst, sgst, igst))
        taxable += amount
        tot_cgst += cgst
        tot_sgst += sgst
        tot_igst += igst

    taxable = money(taxable)
    tot_cgst = money(tot_cgst)
    tot_sgst = money(tot_sgst)
    tot_igst = money(tot_igst)
    grand = money(taxable + tot_cgst + tot_sgst + tot_igst)

    journal: list[LineDraft] = [
        LineDraft(account_code=INVENTORY, debit=taxable, line_narration=bill_no),
    ]
    if tot_cgst > ZERO:
        journal.append(LineDraft(account_code=INPUT_CGST, debit=tot_cgst))
    if tot_sgst > ZERO:
        journal.append(LineDraft(account_code=INPUT_SGST, debit=tot_sgst))
    if tot_igst > ZERO:
        journal.append(LineDraft(account_code=INPUT_IGST, debit=tot_igst))
    journal.append(
        LineDraft(
            account_code=AP_CONTROL,
            credit=grand,
            party_type="vendor",
            party_code=vendor.code,
            branch_code=warehouse.branch_code,
            line_narration=bill_no,
        )
    )

    voucher = post(
        session,
        PostingRequest(
            voucher_date=bill_date,
            voucher_type=VoucherType.PURCHASE,
            narration=f"Purchase {bill_no} {vendor.name}",
            lines=journal,
            source="purchase",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="purchase_bills",
            source_id=bill_no,
        ),
    )

    bill = PurchaseBill(
        bill_no=bill_no,
        grn_no=grn_no,
        bill_date=bill_date,
        fy_code=fy,
        vendor_code=vendor.code,
        vendor_gstin=vendor.gstin,
        vendor_state=vendor.state_code,
        warehouse_code=warehouse.code,
        interstate=interstate,
        taxable=taxable,
        cgst=tot_cgst,
        sgst=tot_sgst,
        igst=tot_igst,
        grand_total=grand,
        voucher_id=voucher.id,
        narration=f"GRN {grn_no}",
    )
    session.add(bill)
    session.flush()

    for line_no, (raw, amount, cgst, sgst, igst) in enumerate(drafted, start=1):
        session.add(
            PurchaseBillLine(
                bill_id=bill.id,
                line_no=line_no,
                product_code=raw.product.code,
                hsn=raw.product.hsn,
                qty=raw.qty,
                rate=money(raw.rate),
                amount=amount,
                gst_rate=money(raw.product.gst_rate),
                cgst=cgst,
                sgst=sgst,
                igst=igst,
            )
        )
        record_stock_move(
            session,
            move_date=bill_date,
            product_code=raw.product.code,
            warehouse_code=warehouse.code,
            qty_in=raw.qty,
            qty_out=ZERO,
            rate=money(raw.rate),
            value=amount,
            voucher_id=voucher.id,
            move_type="GRN",
        )
    session.flush()
    return bill
