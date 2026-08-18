from __future__ import annotations

from decimal import Decimal

from ssdv.money import ZERO, money


def gst_split(taxable: Decimal, rate: Decimal, interstate: bool) -> tuple[Decimal, Decimal, Decimal]:
    """Return (cgst, sgst, igst) for a taxable amount.

    Intra-state: CGST + SGST = tax, split half with paise on SGST.
    Inter-state: full tax as IGST.
    """
    tax = money(money(taxable) * money(rate) / Decimal("100"))
    if tax == ZERO:
        return ZERO, ZERO, ZERO
    if interstate:
        return ZERO, ZERO, tax
    cgst = money(tax / Decimal("2"))
    sgst = money(tax - cgst)
    return cgst, sgst, ZERO


def is_interstate(party_state: str, home_state: str) -> bool:
    return party_state != home_state
