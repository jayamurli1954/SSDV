from ssdv.gstin import gstin_check_digit, is_valid_gstin, make_gstin, random_pan
from ssdv.rng import company_rng


def test_check_digit_is_self_consistent() -> None:
    rng = company_rng()
    pan = random_pan(rng, fourth="C")
    gstin = make_gstin("27", pan)
    assert len(gstin) == 15
    assert gstin[-1] == gstin_check_digit(gstin[:14])
    assert is_valid_gstin(gstin)
    assert not is_valid_gstin(gstin[:14] + ("0" if gstin[-1] != "0" else "1"))


def test_make_gstin_embeds_state_and_pan() -> None:
    gstin = make_gstin("24", "AABCA1234A")
    assert gstin.startswith("24AABCA1234A")
    assert is_valid_gstin(gstin)
