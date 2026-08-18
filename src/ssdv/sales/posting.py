from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingError, PostingRequest, post
from ssdv.fy import fy_code
from ssdv.gl import AR_CONTROL, COGS, INVENTORY, OUTPUT_CGST, OUTPUT_IGST, OUTPUT_SGST, SALES
from ssdv.gst import gst_split, is_interstate
from ssdv.inventory.stock import record_stock_move, stock_quantity, stock_value
from ssdv.models import (
    Customer,
    Product,
    SalesInvoice,
    SalesInvoiceLine,
    VoucherType,
    Warehouse,
)
from ssdv.money import ZERO, money
from ssdv.paths import load_company


@dataclass(frozen=True)
class SalesLineInput:
    product: Product
    qty: Decimal
    rate: Decimal


def _next_doc_no(session: Session, fy: str) -> int:
    count = session.scalar(
        select(func.count()).select_from(SalesInvoice).where(SalesInvoice.fy_code == fy)
    )
    return int(count or 0) + 1


def post_sale(
    session: Session,
    *,
    invoice_date: date,
    customer: Customer,
    warehouse: Warehouse,
    lines: list[SalesLineInput],
    company: dict | None = None,
    scenario: str | None = None,
) -> SalesInvoice:
    if not lines:
        raise ValueError("A sales invoice needs at least one line")

    cfg = company or load_company()
    home_state = str(cfg["accounting"]["home_state_code"])
    if customer.state_code is None:
        raise ValueError(f"Customer {customer.code} has no state")
    interstate = is_interstate(customer.state_code, home_state)
    fy = fy_code(invoice_date)
    seq = _next_doc_no(session, fy)
    invoice_no = f"SAL/{fy}/{seq:06d}"
    dispatch_no = f"DIS/{fy}/{seq:06d}"

    remaining_qty: dict[str, Decimal] = {}
    remaining_value: dict[str, Decimal] = {}
    drafted: list[tuple[SalesLineInput, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]] = []
    taxable = ZERO
    tot_cgst = ZERO
    tot_sgst = ZERO
    tot_igst = ZERO
    tot_cogs = ZERO

    for raw in lines:
        if raw.qty <= ZERO or raw.rate <= ZERO:
            raise PostingError(f"Invalid qty/rate for {raw.product.code}")
        code = raw.product.code
        if code not in remaining_qty:
            remaining_qty[code] = stock_quantity(session, invoice_date, code)
            remaining_value[code] = stock_value(session, invoice_date, code)
        avail_qty = remaining_qty[code]
        avail_value = remaining_value[code]
        if raw.qty > avail_qty:
            raise PostingError(
                f"Insufficient stock for {code}: need {raw.qty}, have {avail_qty} on {invoice_date}"
            )
        if avail_qty <= ZERO or avail_value <= ZERO:
            raise PostingError(f"No valued stock for {code} on {invoice_date}")

        if raw.qty == avail_qty:
            cogs_value = money(avail_value)
            cogs_rate = money(avail_value / avail_qty)
        else:
            cogs_rate = money(avail_value / avail_qty)
            cogs_value = money(raw.qty * cogs_rate)

        amount = money(raw.qty * raw.rate)
        cgst, sgst, igst = gst_split(amount, money(raw.product.gst_rate), interstate)
        drafted.append((raw, amount, cgst, sgst, igst, cogs_rate, cogs_value))
        taxable += amount
        tot_cgst += cgst
        tot_sgst += sgst
        tot_igst += igst
        tot_cogs += cogs_value
        remaining_qty[code] = avail_qty - raw.qty
        remaining_value[code] = money(avail_value - cogs_value)

    taxable = money(taxable)
    tot_cgst = money(tot_cgst)
    tot_sgst = money(tot_sgst)
    tot_igst = money(tot_igst)
    tot_cogs = money(tot_cogs)
    grand = money(taxable + tot_cgst + tot_sgst + tot_igst)
    if tot_cogs <= ZERO:
        raise PostingError(f"{invoice_no} has zero COGS")

    journal: list[LineDraft] = [
        LineDraft(
            account_code=AR_CONTROL,
            debit=grand,
            party_type="customer",
            party_code=customer.code,
            branch_code=warehouse.branch_code,
            line_narration=invoice_no,
        ),
        LineDraft(account_code=SALES, credit=taxable, line_narration=invoice_no),
    ]
    if tot_cgst > ZERO:
        journal.append(LineDraft(account_code=OUTPUT_CGST, credit=tot_cgst))
    if tot_sgst > ZERO:
        journal.append(LineDraft(account_code=OUTPUT_SGST, credit=tot_sgst))
    if tot_igst > ZERO:
        journal.append(LineDraft(account_code=OUTPUT_IGST, credit=tot_igst))
    journal.append(LineDraft(account_code=COGS, debit=tot_cogs, line_narration=invoice_no))
    journal.append(LineDraft(account_code=INVENTORY, credit=tot_cogs, line_narration=invoice_no))

    voucher = post(
        session,
        PostingRequest(
            voucher_date=invoice_date,
            voucher_type=VoucherType.SALE,
            narration=f"Sale {invoice_no} {customer.name}",
            lines=journal,
            source="sale",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="sales_invoices",
            source_id=invoice_no,
        ),
    )

    invoice = SalesInvoice(
        invoice_no=invoice_no,
        dispatch_no=dispatch_no,
        invoice_date=invoice_date,
        fy_code=fy,
        customer_code=customer.code,
        customer_gstin=customer.gstin,
        customer_state=customer.state_code,
        warehouse_code=warehouse.code,
        interstate=interstate,
        taxable=taxable,
        cgst=tot_cgst,
        sgst=tot_sgst,
        igst=tot_igst,
        grand_total=grand,
        cogs=tot_cogs,
        voucher_id=voucher.id,
        narration=f"Dispatch {dispatch_no}",
    )
    session.add(invoice)
    session.flush()

    for line_no, (raw, amount, cgst, sgst, igst, cogs_rate, cogs_value) in enumerate(drafted, start=1):
        invoice.lines.append(
            SalesInvoiceLine(
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
                cogs_rate=cogs_rate,
                cogs_value=cogs_value,
            )
        )
        record_stock_move(
            session,
            move_date=invoice_date,
            product_code=raw.product.code,
            warehouse_code=warehouse.code,
            qty_in=ZERO,
            qty_out=raw.qty,
            rate=cogs_rate,
            value=cogs_value,
            voucher_id=voucher.id,
            move_type="ISSUE",
        )
    session.flush()
    return invoice
