from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingError, PostingRequest, post
from ssdv.fy import fy_code
from ssdv.gl import BANK_CHARGES, EXPENSES_PAYABLE, INTEREST_LOAN, TERM_LOAN
from ssdv.models import BankCharge, LoanEmi, VoucherType
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.seq import next_no


def post_bank_charge(
    session: Session,
    *,
    charge_date: date,
    bank_gl: str,
    amount: Decimal,
    accrued: bool = False,
    company: dict | None = None,
    scenario: str | None = None,
) -> BankCharge:
    amount = money(amount)
    if amount <= ZERO:
        raise PostingError("Bank charge must be positive")
    cfg = company or load_company()
    credit_gl = EXPENSES_PAYABLE if accrued else bank_gl
    voucher = post(
        session,
        PostingRequest(
            voucher_date=charge_date,
            voucher_type=VoucherType.JOURNAL,
            narration=f"Bank charge {bank_gl}",
            lines=[
                LineDraft(account_code=BANK_CHARGES, debit=amount, line_narration=bank_gl),
                LineDraft(account_code=credit_gl, credit=amount, line_narration=bank_gl),
            ],
            source="bank_charge",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="bank_charges",
            source_id=f"CHG/{fy_code(charge_date)}/{bank_gl}/{charge_date.isoformat()}",
        ),
    )
    row = BankCharge(
        charge_date=charge_date,
        fy_code=fy_code(charge_date),
        bank_gl=bank_gl,
        amount=amount,
        expense_gl=BANK_CHARGES,
        accrued=accrued,
        voucher_id=voucher.id,
    )
    session.add(row)
    session.flush()
    return row


def post_emi(
    session: Session,
    *,
    emi_date: date,
    principal: Decimal,
    interest: Decimal,
    bank_gl: str | None,
    company: dict | None = None,
    scenario: str | None = None,
) -> LoanEmi:
    principal = money(principal)
    interest = money(interest)
    if interest <= ZERO and principal <= ZERO:
        raise PostingError("EMI needs interest or principal")
    cfg = company or load_company()
    fy = fy_code(emi_date)
    seq = next_no(session, LoanEmi, LoanEmi.fy_code, fy)
    emi_no = f"EMI/{fy}/{seq:06d}"
    lines: list[LineDraft] = []
    if interest > ZERO:
        lines.append(LineDraft(account_code=INTEREST_LOAN, debit=interest, line_narration=emi_no))
    if bank_gl is None:
        if principal > ZERO:
            raise PostingError("Cannot reduce principal without a bank payment")
        lines.append(
            LineDraft(account_code=EXPENSES_PAYABLE, credit=interest, line_narration=emi_no)
        )
    else:
        if principal > ZERO:
            lines.append(LineDraft(account_code=TERM_LOAN, debit=principal, line_narration=emi_no))
        lines.append(
            LineDraft(
                account_code=bank_gl,
                credit=money(principal + interest),
                line_narration=emi_no,
            )
        )
    voucher = post(
        session,
        PostingRequest(
            voucher_date=emi_date,
            voucher_type=VoucherType.PAYMENT,
            narration=f"Term loan EMI {emi_no}",
            lines=lines,
            source="emi",
            scenario=scenario or cfg.get("generator", {}).get("scenario"),
            source_table="loan_emis",
            source_id=emi_no,
        ),
    )
    row = LoanEmi(
        emi_no=emi_no,
        emi_date=emi_date,
        fy_code=fy,
        principal=principal if bank_gl else ZERO,
        interest=interest,
        bank_gl=bank_gl,
        voucher_id=voucher.id,
    )
    session.add(row)
    session.flush()
    return row
