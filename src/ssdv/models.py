from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


class VoucherType(str, Enum):
    OPENING = "OPENING"
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"
    EXPENSE = "EXPENSE"
    JOURNAL = "JOURNAL"
    CONTRA = "CONTRA"
    CREDIT_NOTE = "CREDIT_NOTE"
    DEBIT_NOTE = "DEBIT_NOTE"
    DEPRECIATION = "DEPRECIATION"
    CLOSING = "CLOSING"
    GST_PAYMENT = "GST_PAYMENT"


class Account(Base):
    __tablename__ = "accounts"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    subtype: Mapped[str] = mapped_column(String(32), nullable=False)
    postable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = (UniqueConstraint("voucher_type", "fy_code", "voucher_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_type: Mapped[str] = mapped_column(String(24), nullable=False)
    voucher_no: Mapped[int] = mapped_column(Integer, nullable=False)
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    narration: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    lines: Mapped[list[JournalLine]] = relationship(
        back_populates="voucher",
        cascade="all, delete-orphan",
        order_by="JournalLine.line_no",
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_non_negative_amounts"),
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_one_sided_line",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False, index=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    party_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    party_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    branch_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cost_centre: Mapped[str | None] = mapped_column(String(16), nullable=True)
    line_narration: Mapped[str | None] = mapped_column(String(255), nullable=True)

    voucher: Mapped[Voucher] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship()


class Customer(Base):
    __tablename__ = "customers"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str | None] = mapped_column(String(64))
    state_code: Mapped[str | None] = mapped_column(String(2))
    pan: Mapped[str | None] = mapped_column(String(10), unique=True)
    gstin: Mapped[str | None] = mapped_column(String(15), unique=True)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    credit_days: Mapped[int | None] = mapped_column(Integer)
    industry: Mapped[str | None] = mapped_column(String(64))
    tier: Mapped[str | None] = mapped_column(String(16))
    branch_code: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Vendor(Base):
    __tablename__ = "vendors"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str | None] = mapped_column(String(64))
    state_code: Mapped[str | None] = mapped_column(String(2))
    pan: Mapped[str | None] = mapped_column(String(10), unique=True)
    gstin: Mapped[str | None] = mapped_column(String(15), unique=True)
    payment_days: Mapped[int | None] = mapped_column(Integer)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    uom: Mapped[str] = mapped_column(String(16), default="NOS")
    hsn: Mapped[str | None] = mapped_column(String(8))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=18)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reorder_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Employee(Base):
    __tablename__ = "employees"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    department: Mapped[str | None] = mapped_column(String(64))
    monthly_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    joining_date: Mapped[date | None] = mapped_column(Date)
    branch_code: Mapped[str | None] = mapped_column(String(16))
    cost_centre: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Branch(Base):
    __tablename__ = "branches"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str | None] = mapped_column(String(64))
    state_code: Mapped[str | None] = mapped_column(String(2))


class Warehouse(Base):
    __tablename__ = "warehouses"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    branch_code: Mapped[str | None] = mapped_column(String(16), ForeignKey("branches.code"))


class BankMaster(Base):
    __tablename__ = "banks"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gl_code: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False)
    ifsc: Mapped[str | None] = mapped_column(String(11))
    account_no: Mapped[str | None] = mapped_column(String(32))
    od_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))


class CostCentre(Base):
    __tablename__ = "cost_centres"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(32))


class StockMove(Base):
    __tablename__ = "stock_moves"
    __table_args__ = (
        CheckConstraint("qty_in >= 0 AND qty_out >= 0", name="ck_stock_qty_non_negative"),
        CheckConstraint("NOT (qty_in = 0 AND qty_out = 0)", name="ck_stock_qty_nonzero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    move_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"), nullable=False, index=True)
    warehouse_code: Mapped[str] = mapped_column(ForeignKey("warehouses.code"), nullable=False)
    qty_in: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    qty_out: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    voucher_id: Mapped[int | None] = mapped_column(ForeignKey("vouchers.id"), nullable=True)
    move_type: Mapped[str] = mapped_column(String(16), nullable=False)


class PurchaseBill(Base):
    __tablename__ = "purchase_bills"
    __table_args__ = (UniqueConstraint("bill_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_no: Mapped[str] = mapped_column(String(32), nullable=False)
    grn_no: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    vendor_code: Mapped[str] = mapped_column(ForeignKey("vendors.code"), nullable=False, index=True)
    vendor_gstin: Mapped[str | None] = mapped_column(String(15))
    vendor_state: Mapped[str] = mapped_column(String(2), nullable=False)
    warehouse_code: Mapped[str] = mapped_column(ForeignKey("warehouses.code"), nullable=False)
    interstate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)
    narration: Mapped[str | None] = mapped_column(String(255))

    lines: Mapped[list[PurchaseBillLine]] = relationship(
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="PurchaseBillLine.line_no",
    )


class PurchaseBillLine(Base):
    __tablename__ = "purchase_bill_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("purchase_bills.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"), nullable=False)
    hsn: Mapped[str | None] = mapped_column(String(8))
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)

    bill: Mapped[PurchaseBill] = relationship(back_populates="lines")


class SalesInvoice(Base):
    __tablename__ = "sales_invoices"
    __table_args__ = (UniqueConstraint("invoice_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(String(32), nullable=False)
    dispatch_no: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    customer_code: Mapped[str] = mapped_column(ForeignKey("customers.code"), nullable=False, index=True)
    customer_gstin: Mapped[str | None] = mapped_column(String(15))
    customer_state: Mapped[str] = mapped_column(String(2), nullable=False)
    warehouse_code: Mapped[str] = mapped_column(ForeignKey("warehouses.code"), nullable=False)
    interstate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cogs: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)
    narration: Mapped[str | None] = mapped_column(String(255))

    lines: Mapped[list[SalesInvoiceLine]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="SalesInvoiceLine.line_no",
    )


class SalesInvoiceLine(Base):
    __tablename__ = "sales_invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoices.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"), nullable=False)
    hsn: Mapped[str | None] = mapped_column(String(8))
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    cogs_rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cogs_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    invoice: Mapped[SalesInvoice] = relationship(back_populates="lines")


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (UniqueConstraint("receipt_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_no: Mapped[str] = mapped_column(String(32), nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    customer_code: Mapped[str] = mapped_column(ForeignKey("customers.code"), nullable=False, index=True)
    bank_gl: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)
    narration: Mapped[str | None] = mapped_column(String(255))

    allocations: Mapped[list[ReceiptAllocation]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
    )


class ReceiptAllocation(Base):
    __tablename__ = "receipt_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), nullable=False, index=True)
    invoice_no: Mapped[str | None] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    receipt: Mapped[Receipt] = relationship(back_populates="allocations")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("payment_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_no: Mapped[str] = mapped_column(String(32), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    vendor_code: Mapped[str] = mapped_column(ForeignKey("vendors.code"), nullable=False, index=True)
    bank_gl: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)
    narration: Mapped[str | None] = mapped_column(String(255))

    allocations: Mapped[list[PaymentAllocation]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False, index=True)
    bill_no: Mapped[str | None] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="allocations")


class OpexEntry(Base):
    __tablename__ = "opex_entries"
    __table_args__ = (UniqueConstraint("expense_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expense_no: Mapped[str] = mapped_column(String(32), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_code: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payable_gl: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    bank_gl: Mapped[str | None] = mapped_column(ForeignKey("accounts.code"))
    pay_date: Mapped[date | None] = mapped_column(Date)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)
    pay_voucher_id: Mapped[int | None] = mapped_column(ForeignKey("vouchers.id"))
    narration: Mapped[str | None] = mapped_column(String(255))


class BankCharge(Base):
    __tablename__ = "bank_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    charge_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    bank_gl: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    expense_gl: Mapped[str] = mapped_column(ForeignKey("accounts.code"), nullable=False)
    accrued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)


class LoanEmi(Base):
    __tablename__ = "loan_emis"
    __table_args__ = (UniqueConstraint("emi_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emi_no: Mapped[str] = mapped_column(String(32), nullable=False)
    emi_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    principal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    interest: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    bank_gl: Mapped[str | None] = mapped_column(ForeignKey("accounts.code"))
    voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)


class GstSettlement(Base):
    __tablename__ = "gst_settlements"
    __table_args__ = (UniqueConstraint("period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fy_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    output_cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    output_sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    output_igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    input_cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    input_sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    input_igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    itc_cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    itc_sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    itc_igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    payable: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    paid: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    bank_gl: Mapped[str | None] = mapped_column(ForeignKey("accounts.code"))
    setoff_voucher_id: Mapped[int] = mapped_column(ForeignKey("vouchers.id"), nullable=False)
    payment_voucher_id: Mapped[int | None] = mapped_column(ForeignKey("vouchers.id"))


class ScenarioMeta(Base):
    __tablename__ = "scenario_meta"

    scenario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    known_cause: Mapped[str] = mapped_column(String(255), nullable=False)
    golden_explanation: Mapped[str] = mapped_column(Text, nullable=False)


class IngestMeta(Base):
    __tablename__ = "ingest_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str] = mapped_column(String(128), nullable=False)
    journals_path: Mapped[str | None] = mapped_column(String(255))
    first_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_date: Mapped[date] = mapped_column(Date, nullable=False)
