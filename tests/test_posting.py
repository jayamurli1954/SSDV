from datetime import date

import pytest

from ssdv.accounting.posting import LineDraft, PostingError, PostingRequest, post
from ssdv.models import VoucherType
from ssdv.money import money


def _sale_like(
    debit: str = "11800.00", credit_sales: str = "10000.00", credit_gst: str = "1800.00"
) -> PostingRequest:
    return PostingRequest(
        voucher_date=date(2023, 4, 3),
        voucher_type=VoucherType.SALE,
        narration="Test sale",
        lines=[
            LineDraft(account_code="120000", debit=debit),
            LineDraft(account_code="410000", credit=credit_sales),
            LineDraft(account_code="221000", credit=credit_gst),
        ],
        source="test",
    )


def test_post_rejects_unbalanced_voucher(session) -> None:
    request = _sale_like(credit_gst="1800.01")
    with pytest.raises(PostingError, match="Unbalanced voucher"):
        post(session, request)


def test_post_rejects_unknown_account(session) -> None:
    request = PostingRequest(
        voucher_date=date(2023, 4, 3),
        voucher_type=VoucherType.JOURNAL,
        narration="Bad account",
        lines=[
            LineDraft(account_code="999999", debit="100.00"),
            LineDraft(account_code="410000", credit="100.00"),
        ],
    )
    with pytest.raises(PostingError, match="Unknown account"):
        post(session, request)


def test_post_rejects_header_account(session) -> None:
    request = PostingRequest(
        voucher_date=date(2023, 4, 3),
        voucher_type=VoucherType.JOURNAL,
        narration="Header",
        lines=[
            LineDraft(account_code="100000", debit="100.00"),
            LineDraft(account_code="410000", credit="100.00"),
        ],
    )
    with pytest.raises(PostingError, match="not postable"):
        post(session, request)


def test_post_rejects_both_sides_on_one_line(session) -> None:
    request = PostingRequest(
        voucher_date=date(2023, 4, 3),
        voucher_type=VoucherType.JOURNAL,
        narration="Two sided line",
        lines=[
            LineDraft(account_code="110000", debit="100.00", credit="100.00"),
            LineDraft(account_code="410000", credit="100.00"),
        ],
    )
    with pytest.raises(PostingError, match="both debit and credit"):
        post(session, request)


def test_post_accepts_balanced_voucher(session) -> None:
    voucher = post(session, _sale_like())
    assert voucher.fy_code == "FY2023-24"
    assert voucher.voucher_no == 1
    assert voucher.voucher_type == VoucherType.SALE.value
    assert money(sum(line.debit for line in voucher.lines)) == money("11800.00")
