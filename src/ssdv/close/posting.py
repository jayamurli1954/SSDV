from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingRequest, post
from ssdv.accounting.trial_balance import ledger_balance, trial_balance
from ssdv.fy import fy_code
from ssdv.gl import ACCUM_DEP_FURNITURE, DEPRECIATION, FURNITURE, PL_ACCOUNT
from ssdv.models import Voucher, VoucherType
from ssdv.money import ZERO, money
from ssdv.paths import load_company


def _has_voucher(session: Session, voucher_type: str, fy: str) -> bool:
    return (
        session.scalar(
            select(Voucher.id)
            .where(
                Voucher.voucher_type == voucher_type,
                Voucher.fy_code == fy,
            )
            .limit(1)
        )
        is not None
    )


def post_depreciation(
    session: Session,
    fy_ending: date,
    company: dict | None = None,
) -> Voucher | None:
    cfg = company or load_company()
    fy = fy_code(fy_ending)
    if _has_voucher(session, VoucherType.DEPRECIATION.value, fy):
        return None
    gross = ledger_balance(session, FURNITURE, fy_ending)
    if gross <= ZERO:
        return None
    accum = money(-ledger_balance(session, ACCUM_DEP_FURNITURE, fy_ending))
    nbv = money(gross - accum)
    rate = money(cfg["accounting"]["furniture_slm_pct"]) / money("100")
    amount = money(gross * rate)
    amount = min(amount, nbv)
    if amount <= ZERO:
        return None
    return post(
        session,
        PostingRequest(
            voucher_date=fy_ending,
            voucher_type=VoucherType.DEPRECIATION,
            narration=f"SLM depreciation furniture {fy}",
            lines=[
                LineDraft(account_code=DEPRECIATION, debit=amount),
                LineDraft(account_code=ACCUM_DEP_FURNITURE, credit=amount),
            ],
            source="depreciation",
            scenario=cfg.get("generator", {}).get("scenario"),
            source_table="vouchers",
            source_id=f"DEP/{fy}",
        ),
    )


def post_closing(
    session: Session,
    fy_ending: date,
    company: dict | None = None,
) -> Voucher | None:
    cfg = company or load_company()
    fy = fy_code(fy_ending)
    if _has_voucher(session, VoucherType.CLOSING.value, fy):
        return None

    income_lines: list[LineDraft] = []
    expense_lines: list[LineDraft] = []
    income_total = ZERO
    expense_total = ZERO
    for row in trial_balance(session, fy_ending):
        if row.account_type == "income" and row.credit > ZERO:
            income_lines.append(
                LineDraft(account_code=row.account_code, debit=row.credit, line_narration="close")
            )
            income_total = money(income_total + row.credit)
        elif row.account_type == "expense" and row.debit > ZERO:
            expense_lines.append(
                LineDraft(account_code=row.account_code, credit=row.debit, line_narration="close")
            )
            expense_total = money(expense_total + row.debit)

    lines: list[LineDraft] = []
    lines.extend(income_lines)
    if income_total > ZERO:
        lines.append(
            LineDraft(account_code=PL_ACCOUNT, credit=income_total, line_narration="close income")
        )
    if expense_total > ZERO:
        lines.append(
            LineDraft(account_code=PL_ACCOUNT, debit=expense_total, line_narration="close expenses")
        )
    lines.extend(expense_lines)
    if len(lines) < 2:
        return None
    return post(
        session,
        PostingRequest(
            voucher_date=fy_ending,
            voucher_type=VoucherType.CLOSING,
            narration=f"Close {fy} P&L to equity",
            lines=lines,
            source="closing",
            scenario=cfg.get("generator", {}).get("scenario"),
            source_table="vouchers",
            source_id=f"CLS/{fy}",
        ),
    )
