from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.fy import fy_code
from ssdv.models import Account, JournalLine, Voucher, VoucherType
from ssdv.money import ZERO, money


class PostingError(ValueError):
    """Raised when a voucher would violate double-entry rules."""


class LineDraft(BaseModel):
    account_code: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    party_type: str | None = None
    party_code: str | None = None
    branch_code: str | None = None
    cost_centre: str | None = None
    line_narration: str | None = None

    @model_validator(mode="after")
    def quantize_amounts(self) -> LineDraft:
        object.__setattr__(self, "debit", money(self.debit))
        object.__setattr__(self, "credit", money(self.credit))
        return self


class PostingRequest(BaseModel):
    voucher_date: date
    voucher_type: VoucherType
    narration: str
    lines: list[LineDraft] = Field(min_length=2)
    source: str | None = None
    scenario: str | None = None
    source_table: str | None = None
    source_id: str | None = None


def _next_voucher_no(session: Session, voucher_type: str, fy: str) -> int:
    last = session.scalar(
        select(func.max(Voucher.voucher_no)).where(
            Voucher.voucher_type == voucher_type,
            Voucher.fy_code == fy,
        )
    )
    return int(last or 0) + 1


def post(session: Session, request: PostingRequest) -> Voucher:
    if len(request.lines) < 2:
        raise PostingError("A voucher needs at least two lines")

    for line in request.lines:
        if line.debit < ZERO or line.credit < ZERO:
            raise PostingError("Debit and credit must be non-negative")
        if line.debit == ZERO and line.credit == ZERO:
            raise PostingError(f"Line {line.account_code} has zero debit and credit")
        if line.debit > ZERO and line.credit > ZERO:
            raise PostingError(f"Line {line.account_code} has both debit and credit")
        account = session.get(Account, line.account_code)
        if account is None:
            raise PostingError(f"Unknown account {line.account_code}")
        if not account.postable:
            raise PostingError(f"Account {line.account_code} is a header and is not postable")

    total_debit = sum((line.debit for line in request.lines), ZERO)
    total_credit = sum((line.credit for line in request.lines), ZERO)
    if money(total_debit) != money(total_credit):
        raise PostingError(
            f"Unbalanced voucher: debit {money(total_debit)} != credit {money(total_credit)}"
        )

    fy = fy_code(request.voucher_date)
    voucher = Voucher(
        voucher_type=request.voucher_type.value,
        voucher_no=_next_voucher_no(session, request.voucher_type.value, fy),
        voucher_date=request.voucher_date,
        fy_code=fy,
        narration=request.narration,
        source=request.source,
        scenario=request.scenario,
        source_table=request.source_table,
        source_id=request.source_id,
    )
    session.add(voucher)
    session.flush()

    for idx, line in enumerate(request.lines, start=1):
        session.add(
            JournalLine(
                voucher_id=voucher.id,
                line_no=idx,
                account_code=line.account_code,
                debit=line.debit,
                credit=line.credit,
                party_type=line.party_type,
                party_code=line.party_code,
                branch_code=line.branch_code,
                cost_centre=line.cost_centre,
                line_narration=line.line_narration,
            )
        )
    session.flush()
    return voucher
