from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingError, PostingRequest, post
from ssdv.cash.outstanding import (
    bill_outstanding,
    invoice_outstanding,
    opening_ap_outstanding,
    opening_ar_outstanding,
)
from ssdv.fy import fy_code
from ssdv.gl import AP_CONTROL, AR_CONTROL
from ssdv.models import (
    Customer,
    Payment,
    PaymentAllocation,
    PurchaseBill,
    Receipt,
    ReceiptAllocation,
    SalesInvoice,
    Vendor,
    VoucherType,
)
from ssdv.money import ZERO, money
from ssdv.paths import load_company


def _next_no(session: Session, model: type, fy_column, fy: str) -> int:
    count = session.scalar(select(func.count()).select_from(model).where(fy_column == fy))
    return int(count or 0) + 1


def post_receipt(
    session: Session,
    *,
    receipt_date: date,
    customer: Customer,
    bank_gl: str,
    amount: Decimal,
    allocations: list[tuple[str | None, Decimal]],
    company: dict | None = None,
    scenario: str | None = None,
) -> Receipt:
    amount = money(amount)
    if amount <= ZERO:
        raise PostingError("Receipt amount must be positive")
    alloc_total = money(sum((money(a) for _, a in allocations), ZERO))
    if alloc_total != amount:
        raise PostingError(f"Receipt allocations {alloc_total} != amount {amount}")

    for invoice_no, alloc_amt in allocations:
        alloc_amt = money(alloc_amt)
        if alloc_amt <= ZERO:
            raise PostingError("Allocation must be positive")
        if invoice_no is None:
            due = opening_ar_outstanding(session, customer.code, receipt_date)
        else:
            invoice = session.scalar(
                select(SalesInvoice).where(SalesInvoice.invoice_no == invoice_no)
            )
            if invoice is None:
                raise PostingError(f"Unknown invoice {invoice_no}")
            if invoice.customer_code != customer.code:
                raise PostingError(f"{invoice_no} does not belong to {customer.code}")
            if invoice.invoice_date > receipt_date:
                raise PostingError(f"Cannot collect {invoice_no} before the invoice date")
            due = invoice_outstanding(session, invoice, receipt_date)
        if alloc_amt > due:
            raise PostingError(f"Over-allocation {alloc_amt} against due {due}")

    cfg = company or load_company()
    fy = fy_code(receipt_date)
    seq = _next_no(session, Receipt, Receipt.fy_code, fy)
    receipt_no = f"RCT/{fy}/{seq:06d}"

    voucher = post(
        session,
        PostingRequest(
            voucher_date=receipt_date,
            voucher_type=VoucherType.RECEIPT,
            narration=f"Receipt {receipt_no} {customer.name}",
            lines=[
                LineDraft(account_code=bank_gl, debit=amount, line_narration=receipt_no),
                LineDraft(
                    account_code=AR_CONTROL,
                    credit=amount,
                    party_type="customer",
                    party_code=customer.code,
                    line_narration=receipt_no,
                ),
            ],
            source="receipt",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="receipts",
            source_id=receipt_no,
        ),
    )
    receipt = Receipt(
        receipt_no=receipt_no,
        receipt_date=receipt_date,
        fy_code=fy,
        customer_code=customer.code,
        bank_gl=bank_gl,
        amount=amount,
        voucher_id=voucher.id,
        narration=f"Collection {customer.code}",
    )
    session.add(receipt)
    session.flush()
    for invoice_no, alloc_amt in allocations:
        receipt.allocations.append(
            ReceiptAllocation(invoice_no=invoice_no, amount=money(alloc_amt))
        )
    session.flush()
    return receipt


def post_payment(
    session: Session,
    *,
    payment_date: date,
    vendor: Vendor,
    bank_gl: str,
    amount: Decimal,
    allocations: list[tuple[str | None, Decimal]],
    company: dict | None = None,
    scenario: str | None = None,
) -> Payment:
    amount = money(amount)
    if amount <= ZERO:
        raise PostingError("Payment amount must be positive")
    alloc_total = money(sum((money(a) for _, a in allocations), ZERO))
    if alloc_total != amount:
        raise PostingError(f"Payment allocations {alloc_total} != amount {amount}")

    for bill_no, alloc_amt in allocations:
        alloc_amt = money(alloc_amt)
        if alloc_amt <= ZERO:
            raise PostingError("Allocation must be positive")
        if bill_no is None:
            due = opening_ap_outstanding(session, vendor.code, payment_date)
        else:
            bill = session.scalar(select(PurchaseBill).where(PurchaseBill.bill_no == bill_no))
            if bill is None:
                raise PostingError(f"Unknown bill {bill_no}")
            if bill.vendor_code != vendor.code:
                raise PostingError(f"{bill_no} does not belong to {vendor.code}")
            if bill.bill_date > payment_date:
                raise PostingError(f"Cannot pay {bill_no} before the bill date")
            due = bill_outstanding(session, bill, payment_date)
        if alloc_amt > due:
            raise PostingError(f"Over-allocation {alloc_amt} against due {due}")

    cfg = company or load_company()
    fy = fy_code(payment_date)
    seq = _next_no(session, Payment, Payment.fy_code, fy)
    payment_no = f"PMT/{fy}/{seq:06d}"

    voucher = post(
        session,
        PostingRequest(
            voucher_date=payment_date,
            voucher_type=VoucherType.PAYMENT,
            narration=f"Payment {payment_no} {vendor.name}",
            lines=[
                LineDraft(
                    account_code=AP_CONTROL,
                    debit=amount,
                    party_type="vendor",
                    party_code=vendor.code,
                    line_narration=payment_no,
                ),
                LineDraft(account_code=bank_gl, credit=amount, line_narration=payment_no),
            ],
            source="payment",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="payments",
            source_id=payment_no,
        ),
    )
    payment = Payment(
        payment_no=payment_no,
        payment_date=payment_date,
        fy_code=fy,
        vendor_code=vendor.code,
        bank_gl=bank_gl,
        amount=amount,
        voucher_id=voucher.id,
        narration=f"Payment {vendor.code}",
    )
    session.add(payment)
    session.flush()
    for bill_no, alloc_amt in allocations:
        payment.allocations.append(PaymentAllocation(bill_no=bill_no, amount=money(alloc_amt)))
    session.flush()
    return payment
