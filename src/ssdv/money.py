from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal | float | str) -> Decimal:
    if isinstance(value, Decimal):
        quantized = value
    else:
        quantized = Decimal(str(value))
    return quantized.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
