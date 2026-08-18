from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ssdv.accounting.posting import LineDraft, PostingError, PostingRequest, post
from ssdv.fy import fy_code
from ssdv.gl import (
    GST_PAYABLE,
    INPUT_CGST,
    INPUT_IGST,
    INPUT_SGST,
    OUTPUT_CGST,
    OUTPUT_IGST,
    OUTPUT_SGST,
)
from ssdv.models import GstSettlement, VoucherType
from ssdv.money import ZERO, money
from ssdv.paths import load_company


def post_gst_settlement(
    session: Session,
    *,
    period: str,
    period_end: date,
    settlement_date: date,
    output_cgst: Decimal,
    output_sgst: Decimal,
    output_igst: Decimal,
    input_cgst: Decimal,
    input_sgst: Decimal,
    input_igst: Decimal,
    paid: Decimal = ZERO,
    bank_gl: str | None = None,
    company: dict | None = None,
    scenario: str | None = None,
) -> GstSettlement:
    out_c, out_s, out_i = money(output_cgst), money(output_sgst), money(output_igst)
    in_c, in_s, in_i = money(input_cgst), money(input_sgst), money(input_igst)
    itc_c = min(in_c, out_c)
    itc_s = min(in_s, out_s)
    itc_i = min(in_i, out_i)
    payable = money((out_c - itc_c) + (out_s - itc_s) + (out_i - itc_i))
    paid = money(paid)
    if paid > payable:
        raise PostingError("GST payment exceeds payable")
    if paid > ZERO and bank_gl is None:
        raise PostingError("GST payment needs a bank")

    lines: list[LineDraft] = []
    if out_c > ZERO:
        lines.append(LineDraft(account_code=OUTPUT_CGST, debit=out_c))
    if out_s > ZERO:
        lines.append(LineDraft(account_code=OUTPUT_SGST, debit=out_s))
    if out_i > ZERO:
        lines.append(LineDraft(account_code=OUTPUT_IGST, debit=out_i))
    if itc_c > ZERO:
        lines.append(LineDraft(account_code=INPUT_CGST, credit=itc_c))
    if itc_s > ZERO:
        lines.append(LineDraft(account_code=INPUT_SGST, credit=itc_s))
    if itc_i > ZERO:
        lines.append(LineDraft(account_code=INPUT_IGST, credit=itc_i))
    if payable > ZERO:
        lines.append(LineDraft(account_code=GST_PAYABLE, credit=payable))
    if not lines:
        raise PostingError("GST settlement has no lines")

    cfg = company or load_company()
    scenario = scenario or cfg.get("generator", {}).get("scenario")
    setoff = post(
        session,
        PostingRequest(
            voucher_date=settlement_date,
            voucher_type=VoucherType.GST_PAYMENT,
            narration=f"GST set-off {period}",
            lines=lines,
            source="gst_setoff",
            scenario=scenario,
            source_table="gst_settlements",
            source_id=f"GST/{period}",
        ),
    )
    pay_id = None
    if paid > ZERO and bank_gl:
        pay = post(
            session,
            PostingRequest(
                voucher_date=settlement_date,
                voucher_type=VoucherType.GST_PAYMENT,
                narration=f"GST paid {period}",
                lines=[
                    LineDraft(account_code=GST_PAYABLE, debit=paid),
                    LineDraft(account_code=bank_gl, credit=paid),
                ],
                source="gst_payment",
                scenario=scenario,
                source_table="gst_settlements",
                source_id=f"GST/{period}/PAY",
            ),
        )
        pay_id = pay.id

    row = GstSettlement(
        period=period,
        period_end=period_end,
        settlement_date=settlement_date,
        fy_code=fy_code(period_end),
        output_cgst=out_c,
        output_sgst=out_s,
        output_igst=out_i,
        input_cgst=in_c,
        input_sgst=in_s,
        input_igst=in_i,
        itc_cgst=itc_c,
        itc_sgst=itc_s,
        itc_igst=itc_i,
        payable=payable,
        paid=paid,
        bank_gl=bank_gl if paid > ZERO else None,
        setoff_voucher_id=setoff.id,
        payment_voucher_id=pay_id,
    )
    session.add(row)
    session.flush()
    return row
