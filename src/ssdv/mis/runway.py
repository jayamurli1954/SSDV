"""Cash runway and the interactive what-if on top of it. Deterministic; no LLM math.

Burn is the average monthly operating loss (sales - COGS - opex) over the most recent
complete months of posted journals. Runway is cash divided by that burn. Books are
never changed: every lever only rescales the posted monthly averages.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ssdv.money import ZERO, money

RUNWAY_WINDOW_MONTHS = 3
RUNWAY_METHOD = (
    "Burn is the average monthly operating loss (sales - COGS - opex) over the last "
    f"{RUNWAY_WINDOW_MONTHS} complete months of posted journals. Runway is cash / burn. "
    "Levers rescale those averages; COGS moves with sales at the same margin. "
    "Books are not changed."
)

_TENTH = Decimal("0.1")
_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class RunwayBase:
    """Posted monthly averages the runway and every what-if lever start from."""

    monthly_sales: Decimal
    monthly_cogs: Decimal
    monthly_opex: Decimal
    cash: Decimal
    ar: Decimal
    months_used: int
    partial_month: bool

    @property
    def monthly_result(self) -> Decimal:
        return money(self.monthly_sales - self.monthly_cogs - self.monthly_opex)

    @property
    def burn(self) -> Decimal:
        return max(ZERO, money(-self.monthly_result))

    @property
    def runway(self) -> Decimal | None:
        return runway_months(self.cash, self.burn)


@dataclass(frozen=True)
class Levers:
    sales_change_pct: Decimal = ZERO
    opex_change_pct: Decimal = ZERO
    new_monthly_cost: Decimal = ZERO
    ar_collected: Decimal = ZERO


@dataclass(frozen=True)
class RunwayResult:
    monthly_sales: Decimal
    monthly_result: Decimal
    burn: Decimal
    cash: Decimal
    runway: Decimal | None


def runway_months(cash: Decimal, burn: Decimal) -> Decimal | None:
    """Months of cash left at this burn. None means the books are not burning cash."""
    if burn <= ZERO:
        return None
    if cash <= ZERO:
        return Decimal("0.0")
    return (cash / burn).quantize(_TENTH, rounding=ROUND_HALF_UP)


def _is_month_end(day: Any) -> bool:
    return day.day == monthrange(day.year, day.month)[1]


def _average(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        return ZERO
    return money(sum(values, ZERO) / Decimal(len(values)))


def runway_base(snap: Any, *, window: int = RUNWAY_WINDOW_MONTHS) -> RunwayBase:
    series = snap.series
    count = len(series.sales)
    partial = count > 0 and not _is_month_end(snap.as_of)
    # Drop the partial current month whenever a complete month is available.
    stop = count - 1 if partial and count > 1 else count
    start = max(0, stop - window)
    return RunwayBase(
        monthly_sales=_average(tuple(series.sales[start:stop])),
        monthly_cogs=_average(tuple(series.cogs[start:stop])),
        monthly_opex=_average(tuple(series.opex[start:stop])),
        cash=money(snap.cash),
        ar=money(snap.ar),
        months_used=stop - start,
        partial_month=partial and count == 1,
    )


def _result(base: RunwayBase) -> RunwayResult:
    return RunwayResult(
        monthly_sales=base.monthly_sales,
        monthly_result=base.monthly_result,
        burn=base.burn,
        cash=base.cash,
        runway=base.runway,
    )


def simulate_runway(base: RunwayBase, levers: Levers) -> tuple[RunwayResult, RunwayResult]:
    """Return (baseline, simulated). Collections are capped at the AR on the books."""
    sales_factor = max(Decimal(0), Decimal(1) + Decimal(levers.sales_change_pct) / _HUNDRED)
    opex_factor = max(Decimal(0), Decimal(1) + Decimal(levers.opex_change_pct) / _HUNDRED)
    sales = money(base.monthly_sales * sales_factor)
    cogs = money(base.monthly_cogs * sales_factor)
    opex = money(base.monthly_opex * opex_factor + max(ZERO, money(levers.new_monthly_cost)))
    result = money(sales - cogs - opex)
    burn = max(ZERO, money(-result))
    collected = min(max(ZERO, money(levers.ar_collected)), max(ZERO, base.ar))
    cash = money(base.cash + collected)
    simulated = RunwayResult(
        monthly_sales=sales,
        monthly_result=result,
        burn=burn,
        cash=cash,
        runway=runway_months(cash, burn),
    )
    return _result(base), simulated


def runway_text(runway: Decimal | None) -> str:
    return "Not burning" if runway is None else f"{runway} months"


def base_as_dict(base: RunwayBase) -> dict[str, Any]:
    return {
        "monthly_sales": str(base.monthly_sales),
        "monthly_cogs": str(base.monthly_cogs),
        "monthly_opex": str(base.monthly_opex),
        "monthly_result": str(base.monthly_result),
        "burn": str(base.burn),
        "cash": str(base.cash),
        "ar": str(base.ar),
        "months_used": base.months_used,
        "partial_month": base.partial_month,
        "runway_months": None if base.runway is None else str(base.runway),
    }


def base_from_dict(data: dict[str, Any]) -> RunwayBase:
    return RunwayBase(
        monthly_sales=money(str(data.get("monthly_sales") or "0")),
        monthly_cogs=money(str(data.get("monthly_cogs") or "0")),
        monthly_opex=money(str(data.get("monthly_opex") or "0")),
        cash=money(str(data.get("cash") or "0")),
        ar=money(str(data.get("ar") or "0")),
        months_used=int(data.get("months_used") or 0),
        partial_month=bool(data.get("partial_month")),
    )
