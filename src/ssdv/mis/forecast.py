from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ssdv.mis.kpis import MisSnapshot
from ssdv.money import ZERO, money

FORECAST_HORIZONS = (30, 60, 90)
_TIMED_BUCKET = {30: "0-30", 60: "31-60", 90: "61-90"}
FORECAST_METHOD = (
    "Open AR and AP in 0-30 / 31-60 / 61-90 convert on those horizons. "
    "GST net liability and salary payable are 30-day outflows. "
    "AR 90+ and AR with no invoice aging are not timed. No future sales."
)


@dataclass(frozen=True)
class CashHorizon:
    days: int
    label: str
    ar_in: Decimal
    ap_out: Decimal
    gst_out: Decimal
    salary_out: Decimal
    net: Decimal
    cash: Decimal


@dataclass(frozen=True)
class CashForecast:
    opening_cash: Decimal
    gst_input: Decimal
    gst_output: Decimal
    gst_net: Decimal
    blocked_ar: Decimal
    method: str
    horizons: tuple[CashHorizon, ...]


def _aging_amount(aging: dict[str, Decimal], key: str) -> Decimal:
    return money(aging.get(key, ZERO))


def _unaged(gl_balance: Decimal, aging: dict[str, Decimal]) -> Decimal:
    aged = money(aging.get("total", ZERO))
    gap = money(gl_balance - aged)
    return max(ZERO, gap)


def cash_forecast(snap: MisSnapshot) -> CashForecast:
    """30/60/90 cash from posted AR/AP buckets. Not a sales plan."""
    cash = money(snap.cash)
    gst_due = max(ZERO, snap.gst_net)
    salary = max(ZERO, snap.salary_payable)
    unaged_ap = _unaged(snap.ap, snap.ap_aging)
    running = cash
    rows: list[CashHorizon] = []
    for days in FORECAST_HORIZONS:
        bucket = _TIMED_BUCKET[days]
        ar_in = _aging_amount(snap.ar_aging, bucket)
        ap_out = _aging_amount(snap.ap_aging, bucket)
        if days == 30:
            ap_out = money(ap_out + unaged_ap)
        gst_out = gst_due if days == 30 else ZERO
        salary_out = salary if days == 30 else ZERO
        net = money(ar_in - ap_out - gst_out - salary_out)
        running = money(running + net)
        rows.append(
            CashHorizon(
                days=days,
                label=f"{days} days",
                ar_in=ar_in,
                ap_out=ap_out,
                gst_out=gst_out,
                salary_out=salary_out,
                net=net,
                cash=running,
            )
        )
    blocked = money(snap.cash_blocked_90 + _unaged(snap.ar, snap.ar_aging))
    return CashForecast(
        opening_cash=cash,
        gst_input=snap.gst_input,
        gst_output=snap.gst_output,
        gst_net=snap.gst_net,
        blocked_ar=blocked,
        method=FORECAST_METHOD,
        horizons=tuple(rows),
    )
