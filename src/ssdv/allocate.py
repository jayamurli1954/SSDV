from __future__ import annotations

from decimal import Decimal

from ssdv.money import ZERO, money


def allocate_total(
    weights: list[float] | list[int] | list[Decimal], total: Decimal
) -> list[Decimal]:
    """Split `total` across weights so the parts sum exactly to `total`."""
    if not weights:
        raise ValueError("weights must be non-empty")
    total = money(total)
    dec_w = [Decimal(str(w)) for w in weights]
    weight_sum = sum(dec_w, ZERO)
    if weight_sum <= 0:
        raise ValueError("weights must sum to a positive number")
    parts = [money(total * w / weight_sum) for w in dec_w]
    parts[-1] = money(total - sum(parts[:-1], ZERO))
    if parts[-1] < ZERO:
        raise ValueError("allocation rounding produced a negative remainder")
    return parts
