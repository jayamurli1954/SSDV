from decimal import Decimal

from ssdv.gst import gst_split, is_interstate
from ssdv.money import money


def test_intra_state_splits_cgst_sgst() -> None:
    cgst, sgst, igst = gst_split(money("1000.00"), money("18.00"), interstate=False)
    assert cgst == money("90.00")
    assert sgst == money("90.00")
    assert igst == money("0")
    assert cgst + sgst + igst == money("180.00")


def test_inter_state_is_igst_only() -> None:
    cgst, sgst, igst = gst_split(money("1000.00"), money("18.00"), interstate=True)
    assert cgst == money("0")
    assert sgst == money("0")
    assert igst == money("180.00")


def test_odd_paise_lands_on_sgst() -> None:
    cgst, sgst, igst = gst_split(money("100.00"), money("18.00"), interstate=False)
    assert cgst + sgst == money("18.00")
    assert igst == money("0")
    assert cgst == money("9.00")
    assert sgst == money("9.00")


def test_zero_rate() -> None:
    cgst, sgst, igst = gst_split(money("500.00"), Decimal("0"), interstate=False)
    assert (cgst, sgst, igst) == (money("0"), money("0"), money("0"))


def test_place_of_supply() -> None:
    assert not is_interstate("27", "27")
    assert is_interstate("24", "27")
