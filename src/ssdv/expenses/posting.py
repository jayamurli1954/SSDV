from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingError, PostingRequest, post
from ssdv.fy import fy_code
from ssdv.models import OpexEntry, VoucherType
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.seq import next_no


def post_opex(
    session: Session,
    *,
    expense_date: date,
    kind: str,
    account_code: str,
    amount: Decimal,
    payable_gl: str,
    company: dict | None = None,
    scenario: str | None = None,
) -> OpexEntry:
    amount = money(amount)
    if amount <= ZERO:
        raise PostingError("Expense amount must be positive")
    cfg = company or load_company()
    fy = fy_code(expense_date)
    seq = next_no(session, OpexEntry, OpexEntry.fy_code, fy)
    expense_no = f"EXP/{fy}/{seq:06d}"
    voucher = post(
        session,
        PostingRequest(
            voucher_date=expense_date,
            voucher_type=VoucherType.EXPENSE,
            narration=f"Expense {expense_no} {kind}",
            lines=[
                LineDraft(account_code=account_code, debit=amount, line_narration=kind),
                LineDraft(account_code=payable_gl, credit=amount, line_narration=kind),
            ],
            source="opex",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="opex_entries",
            source_id=expense_no,
        ),
    )
    entry = OpexEntry(
        expense_no=expense_no,
        expense_date=expense_date,
        fy_code=fy,
        kind=kind,
        account_code=account_code,
        amount=amount,
        payable_gl=payable_gl,
        paid_amount=ZERO,
        voucher_id=voucher.id,
        narration=kind,
    )
    session.add(entry)
    session.flush()
    return entry


def pay_opex(
    session: Session,
    entry: OpexEntry,
    *,
    pay_date: date,
    bank_gl: str,
    amount: Decimal,
    company: dict | None = None,
    scenario: str | None = None,
) -> OpexEntry:
    amount = money(amount)
    due = money(entry.amount - entry.paid_amount)
    if amount <= ZERO:
        raise PostingError("Payment amount must be positive")
    if amount > due:
        raise PostingError(f"Over-payment {amount} against due {due}")
    cfg = company or load_company()
    voucher = post(
        session,
        PostingRequest(
            voucher_date=pay_date,
            voucher_type=VoucherType.JOURNAL,
            narration=f"Pay {entry.expense_no} {entry.kind}",
            lines=[
                LineDraft(
                    account_code=entry.payable_gl, debit=amount, line_narration=entry.expense_no
                ),
                LineDraft(account_code=bank_gl, credit=amount, line_narration=entry.expense_no),
            ],
            source="opex_payment",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="opex_entries",
            source_id=f"{entry.expense_no}-PAY",
        ),
    )
    entry.paid_amount = money(entry.paid_amount + amount)
    entry.bank_gl = bank_gl
    entry.pay_date = pay_date
    entry.pay_voucher_id = voucher.id
    session.flush()
    return entry
