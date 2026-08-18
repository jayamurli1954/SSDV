from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingRequest, post
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.banking.posting import post_bank_charge, post_emi
from ssdv.calendar import load_holidays, next_working_day, previous_working_day
from ssdv.cash.banks import apply_bank, bank_floor, choose_bank, current_bank_balances
from ssdv.fy import iter_month_ends
from ssdv.gl import BANK_HDFC, BANK_ICICI, BANK_OD, EXPENSES_PAYABLE, INTEREST_OD
from ssdv.models import LoanEmi, VoucherType
from ssdv.money import ZERO, money
from ssdv.paths import load_company


def generate_banking(session: Session, company: dict[str, Any] | None = None) -> tuple[int, int]:
    cfg = company or load_company()
    if int(session.scalar(select(func.count()).select_from(LoanEmi)) or 0) > 0:
        return 0, 0

    holidays = load_holidays(cfg)
    skip_sundays = bool(cfg["generator"].get("skip_sundays", True))
    books_start = date.fromisoformat(str(cfg["calendar"]["books_start"]))
    books_end = date.fromisoformat(str(cfg["calendar"]["books_end"]))
    od_limit = money(cfg["accounting"]["od_limit_inr"])
    charge_amt = money(cfg["opex"]["bank_charge"])
    emi_amt = money(cfg["loan"]["emi_inr"])
    rate_monthly = money(cfg["loan"]["annual_rate_pct"]) / Decimal("100") / Decimal("12")
    outstanding = money(cfg["loan"]["principal_inr"])
    balances = current_bank_balances(session, books_end)
    charges = 0
    emis = 0

    for month_end in iter_month_ends(books_start, books_end):
        emi_when = next_working_day(
            date(month_end.year, month_end.month, 5),
            books_end,
            skip_sundays=skip_sundays,
            holidays=holidays,
        )
        charge_when = previous_working_day(month_end, skip_sundays=skip_sundays, holidays=holidays)
        if emi_when is None:
            emi_when = charge_when

        for gl in (BANK_HDFC, BANK_ICICI):
            accrued = money(balances[gl] - charge_amt) < bank_floor(gl, od_limit)
            post_bank_charge(
                session,
                charge_date=charge_when,
                bank_gl=gl,
                amount=charge_amt,
                accrued=accrued,
                company=cfg,
            )
            if not accrued:
                apply_bank(balances, gl, money(-charge_amt))
            charges += 1

        interest = money(outstanding * rate_monthly)
        principal = money(emi_amt - interest)
        if principal < ZERO:
            principal = ZERO
            interest = emi_amt
        if principal > outstanding:
            principal = outstanding
        installment = money(principal + interest)
        bank = choose_bank(balances, installment, od_limit)
        if bank is None:
            post_emi(
                session,
                emi_date=emi_when,
                principal=ZERO,
                interest=interest,
                bank_gl=None,
                company=cfg,
            )
        else:
            post_emi(
                session,
                emi_date=emi_when,
                principal=principal,
                interest=interest,
                bank_gl=bank,
                company=cfg,
            )
            apply_bank(balances, bank, money(-installment))
            outstanding = money(outstanding - principal)
        emis += 1

        od_bal = ledger_balance(session, BANK_OD, charge_when)
        if od_bal < ZERO:
            od_interest = money(money(-od_bal) * rate_monthly)
            if od_interest > ZERO:
                post(
                    session,
                    PostingRequest(
                        voucher_date=charge_when,
                        voucher_type=VoucherType.JOURNAL,
                        narration=f"OD interest {charge_when.isoformat()}",
                        lines=[
                            LineDraft(account_code=INTEREST_OD, debit=od_interest),
                            LineDraft(account_code=EXPENSES_PAYABLE, credit=od_interest),
                        ],
                        source="od_interest",
                        scenario=cfg.get("generator", {}).get("scenario"),
                        source_table="bank_charges",
                        source_id=f"ODINT/{charge_when.isoformat()}",
                    ),
                )
        session.flush()

    return charges, emis
