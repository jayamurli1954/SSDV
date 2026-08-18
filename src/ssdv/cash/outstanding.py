from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.gl import AP_CONTROL, AR_CONTROL
from ssdv.models import (
    JournalLine,
    Payment,
    PaymentAllocation,
    PurchaseBill,
    Receipt,
    ReceiptAllocation,
    SalesInvoice,
    Voucher,
    VoucherType,
)
from ssdv.money import ZERO, money


def opening_ar_amount(session: Session, customer_code: str) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(Voucher.voucher_type == VoucherType.OPENING.value)
        .where(JournalLine.account_code == AR_CONTROL)
        .where(JournalLine.party_type == "customer")
        .where(JournalLine.party_code == customer_code)
    )
    return money(session.scalar(stmt) or 0)


def opening_ap_amount(session: Session, vendor_code: str) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0))
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(Voucher.voucher_type == VoucherType.OPENING.value)
        .where(JournalLine.account_code == AP_CONTROL)
        .where(JournalLine.party_type == "vendor")
        .where(JournalLine.party_code == vendor_code)
    )
    return money(session.scalar(stmt) or 0)


def allocated_to_invoice(session: Session, invoice_no: str, as_of: date) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(ReceiptAllocation.amount), 0))
        .join(Receipt, Receipt.id == ReceiptAllocation.receipt_id)
        .where(ReceiptAllocation.invoice_no == invoice_no)
        .where(Receipt.receipt_date <= as_of)
    )
    return money(session.scalar(stmt) or 0)


def allocated_to_bill(session: Session, bill_no: str, as_of: date) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.bill_no == bill_no)
        .where(Payment.payment_date <= as_of)
    )
    return money(session.scalar(stmt) or 0)


def allocated_to_opening_ar(session: Session, customer_code: str, as_of: date) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(ReceiptAllocation.amount), 0))
        .join(Receipt, Receipt.id == ReceiptAllocation.receipt_id)
        .where(Receipt.customer_code == customer_code)
        .where(ReceiptAllocation.invoice_no.is_(None))
        .where(Receipt.receipt_date <= as_of)
    )
    return money(session.scalar(stmt) or 0)


def allocated_to_opening_ap(session: Session, vendor_code: str, as_of: date) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.vendor_code == vendor_code)
        .where(PaymentAllocation.bill_no.is_(None))
        .where(Payment.payment_date <= as_of)
    )
    return money(session.scalar(stmt) or 0)


def invoice_outstanding(session: Session, invoice: SalesInvoice, as_of: date) -> Decimal:
    return money(invoice.grand_total - allocated_to_invoice(session, invoice.invoice_no, as_of))


def bill_outstanding(session: Session, bill: PurchaseBill, as_of: date) -> Decimal:
    return money(bill.grand_total - allocated_to_bill(session, bill.bill_no, as_of))


def opening_ar_outstanding(session: Session, customer_code: str, as_of: date) -> Decimal:
    return money(
        opening_ar_amount(session, customer_code)
        - allocated_to_opening_ar(session, customer_code, as_of)
    )


def opening_ap_outstanding(session: Session, vendor_code: str, as_of: date) -> Decimal:
    return money(
        opening_ap_amount(session, vendor_code)
        - allocated_to_opening_ap(session, vendor_code, as_of)
    )


def opening_ar_balances(session: Session) -> dict[str, Decimal]:
    stmt = (
        select(
            JournalLine.party_code,
            func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0),
        )
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(Voucher.voucher_type == VoucherType.OPENING.value)
        .where(JournalLine.account_code == AR_CONTROL)
        .where(JournalLine.party_type == "customer")
        .where(JournalLine.party_code.isnot(None))
        .group_by(JournalLine.party_code)
    )
    return {str(code): money(amt) for code, amt in session.execute(stmt) if money(amt) > ZERO}


def opening_ap_balances(session: Session) -> dict[str, Decimal]:
    stmt = (
        select(
            JournalLine.party_code,
            func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0),
        )
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(Voucher.voucher_type == VoucherType.OPENING.value)
        .where(JournalLine.account_code == AP_CONTROL)
        .where(JournalLine.party_type == "vendor")
        .where(JournalLine.party_code.isnot(None))
        .group_by(JournalLine.party_code)
    )
    return {str(code): money(amt) for code, amt in session.execute(stmt) if money(amt) > ZERO}


def invoice_allocation_map(session: Session, as_of: date) -> dict[str, Decimal]:
    stmt = (
        select(
            ReceiptAllocation.invoice_no,
            func.coalesce(func.sum(ReceiptAllocation.amount), 0),
        )
        .join(Receipt, Receipt.id == ReceiptAllocation.receipt_id)
        .where(Receipt.receipt_date <= as_of)
        .where(ReceiptAllocation.invoice_no.isnot(None))
        .group_by(ReceiptAllocation.invoice_no)
    )
    return {str(no): money(amt) for no, amt in session.execute(stmt)}


def bill_allocation_map(session: Session, as_of: date) -> dict[str, Decimal]:
    stmt = (
        select(
            PaymentAllocation.bill_no,
            func.coalesce(func.sum(PaymentAllocation.amount), 0),
        )
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.payment_date <= as_of)
        .where(PaymentAllocation.bill_no.isnot(None))
        .group_by(PaymentAllocation.bill_no)
    )
    return {str(no): money(amt) for no, amt in session.execute(stmt)}


def opening_ar_allocation_map(session: Session, as_of: date) -> dict[str, Decimal]:
    stmt = (
        select(
            Receipt.customer_code,
            func.coalesce(func.sum(ReceiptAllocation.amount), 0),
        )
        .join(ReceiptAllocation, ReceiptAllocation.receipt_id == Receipt.id)
        .where(Receipt.receipt_date <= as_of)
        .where(ReceiptAllocation.invoice_no.is_(None))
        .group_by(Receipt.customer_code)
    )
    return {str(code): money(amt) for code, amt in session.execute(stmt)}


def opening_ap_allocation_map(session: Session, as_of: date) -> dict[str, Decimal]:
    stmt = (
        select(
            Payment.vendor_code,
            func.coalesce(func.sum(PaymentAllocation.amount), 0),
        )
        .join(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
        .where(Payment.payment_date <= as_of)
        .where(PaymentAllocation.bill_no.is_(None))
        .group_by(Payment.vendor_code)
    )
    return {str(code): money(amt) for code, amt in session.execute(stmt)}


def document_ar_outstanding(session: Session, as_of: date) -> Decimal:
    invoice_total = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.grand_total), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    allocated = money(
        session.scalar(
            select(func.coalesce(func.sum(ReceiptAllocation.amount), 0))
            .join(Receipt, Receipt.id == ReceiptAllocation.receipt_id)
            .where(Receipt.receipt_date <= as_of)
        )
        or 0
    )
    opening = money(sum(opening_ar_balances(session).values(), ZERO))
    return money(opening + invoice_total - allocated)


def document_ap_outstanding(session: Session, as_of: date) -> Decimal:
    bill_total = money(
        session.scalar(
            select(func.coalesce(func.sum(PurchaseBill.grand_total), 0)).where(
                PurchaseBill.bill_date <= as_of
            )
        )
        or 0
    )
    allocated = money(
        session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(Payment.payment_date <= as_of)
        )
        or 0
    )
    opening = money(sum(opening_ap_balances(session).values(), ZERO))
    return money(opening + bill_total - allocated)
