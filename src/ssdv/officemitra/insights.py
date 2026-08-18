from __future__ import annotations

from dataclasses import dataclass

from ssdv.mis.benchmarks import build_benchmarks
from ssdv.mis.forecast import cash_forecast
from ssdv.mis.kpis import MisSnapshot
from ssdv.mis.policy import (
    COGS_RATIO_MAX,
    COLLECTION_EFFICIENCY_MIN,
    CUSTOMER_SHARE_MAX,
    DSO_DAYS_MAX,
)
from ssdv.money import ZERO, money


WHY_PROMPTS = (
    "Why did profit fall?",
    "Why is cash negative?",
    "Why is inventory rising?",
    "Why is AR over 90 days up?",
    "Which customers drive concentration?",
)


@dataclass(frozen=True)
class Insight:
    id: str
    surface: str
    text: str
    tone: str


def _inr(amount) -> str:
    return f"{amount:,.2f}"


def _pct(ratio, digits: int = 1) -> str:
    return f"{(ratio * 100):.{digits}f}%"


def build_why(snap: MisSnapshot) -> tuple[Insight, ...]:
    """Drivers taken from monthly series, aging, and named ledger metrics only."""
    out: list[Insight] = []
    series = snap.series
    if len(series.labels) >= 2:
        prev_lab, last_lab = series.labels[-2], series.labels[-1]
        sales_prev, sales_last = series.sales[-2], series.sales[-1]
        gm_prev, gm_last = series.gross_margin[-2], series.gross_margin[-1]
        opex_prev, opex_last = series.opex[-2], series.opex[-1]
        rec_prev, rec_last = series.receipts[-2], series.receipts[-1]
        cogs_prev = series.cogs[-2]
        profit_prev = money(sales_prev - cogs_prev - opex_prev)
        profit_last = snap.monthly_profit
        drivers: list[str] = []
        if gm_last < gm_prev:
            drivers.append(f"gross margin rupees fell from {_inr(gm_prev)} to {_inr(gm_last)}")
        if opex_last > opex_prev:
            drivers.append(
                f"operating expenses rose from {_inr(opex_prev)} to {_inr(opex_last)}"
            )
        if rec_last < rec_prev:
            drivers.append(f"receipts fell from {_inr(rec_prev)} to {_inr(rec_last)}")
        if profit_last < profit_prev and drivers:
            tone = "danger" if profit_last < ZERO else "warning"
            out.append(
                Insight(
                    "why_profit",
                    "why",
                    (
                        f"{last_lab} profit {_inr(profit_last)} vs {prev_lab} {_inr(profit_prev)} "
                        f"because {'; '.join(drivers)}."
                    ),
                    tone,
                )
            )
        elif profit_last < ZERO:
            out.append(
                Insight(
                    "why_profit",
                    "why",
                    (
                        f"{last_lab} profit is negative ({_inr(profit_last)}). "
                        f"Last-month gross margin and opex did not isolate a further driver vs {prev_lab}."
                    ),
                    "danger",
                )
            )
        if (
            sales_last > ZERO
            and series.purchases[-1] > sales_last
            and series.purchases[-1] > series.purchases[-2]
        ):
            out.append(
                Insight(
                    "why_inventory",
                    "why",
                    (
                        f"{last_lab} purchases {_inr(series.purchases[-1])} exceeded sales "
                        f"{_inr(sales_last)} (prior month purchases {_inr(series.purchases[-2])})."
                    ),
                    "warning",
                )
            )

    if snap.cash < ZERO and series.receipts:
        label = series.labels[-1] if series.labels else "Last month"
        last_r = series.receipts[-1]
        last_p = series.payments[-1]
        out.append(
            Insight(
                "why_cash",
                "why",
                (
                    f"Cash position {_inr(snap.cash)}. {label} receipts {_inr(last_r)} vs "
                    f"payments {_inr(last_p)} (net {_inr(money(last_r - last_p))})."
                ),
                "danger",
            )
        )

    overdue = snap.cash_blocked_90
    if overdue > ZERO and snap.ar > ZERO:
        extra = ""
        gap = snap.dso_policy_gap_ar
        if gap is not None:
            extra = (
                f" DSO {snap.dso} days vs 120-day policy implies about {_inr(gap)} extra AR vs policy."
            )
        out.append(
            Insight(
                "why_ar90",
                "why",
                f"Cash sitting in AR 90+ is {_inr(overdue)}.{extra}",
                "danger",
            )
        )
    return tuple(out)


def build_red_flags(snap: MisSnapshot) -> tuple[Insight, ...]:
    """Board exceptions only: DSO policy, negative cash, negative equity, falling profit."""
    flags: list[Insight] = []
    if snap.dso is not None and snap.dso > DSO_DAYS_MAX:
        flags.append(
            Insight(
                "flag_dso",
                "board",
                f"DSO {snap.dso} days exceeds 120-day policy.",
                "danger",
            )
        )
    if snap.cash < ZERO:
        flags.append(
            Insight(
                "flag_cash",
                "board",
                f"Cash position is negative ({_inr(snap.cash)}).",
                "danger",
            )
        )
    if snap.equity < ZERO:
        flags.append(
            Insight(
                "flag_equity",
                "board",
                f"Equity after close is negative ({_inr(snap.equity)}).",
                "danger",
            )
        )
    if len(snap.series.sales) >= 2:
        prev = money(snap.series.sales[-2] - snap.series.cogs[-2] - snap.series.opex[-2])
        last = snap.monthly_profit
        if last < prev:
            flags.append(
                Insight(
                    "flag_profit",
                    "board",
                    f"Last-month profit {_inr(last)} is below prior month {_inr(prev)}.",
                    "danger" if last < ZERO else "warning",
                )
            )
    elif snap.monthly_profit < ZERO:
        flags.append(
            Insight(
                "flag_profit",
                "board",
                f"Last-month profit is negative ({_inr(snap.monthly_profit)}).",
                "danger",
            )
        )
    return tuple(flags)


def build_insights(snap: MisSnapshot, *, limit: int = 18) -> tuple[Insight, ...]:
    """Short lines to show on P&L / aging / CEO / why. Numbers only, no invented cause."""
    out: list[Insight] = []
    if snap.sales_growth is not None:
        direction = "increased" if snap.sales_growth >= ZERO else "decreased"
        out.append(
            Insight(
                "sales_growth",
                "pnl",
                f"Revenue {direction} {_pct(abs(snap.sales_growth))} vs prior YTD.",
                "success" if snap.sales_growth >= ZERO else "danger",
            )
        )
    else:
        out.append(
            Insight(
                "sales_level",
                "pnl",
                f"YTD taxable sales {_inr(snap.fy.sales)} (no prior year in these books).",
                "neutral",
            )
        )

    gm_tone = "success"
    if snap.metrics.cogs_ratio >= COGS_RATIO_MAX or snap.fy.gm_pct < money("0.10"):
        gm_tone = "danger"
    elif snap.fy.gm_pct < money("0.18"):
        gm_tone = "warning"
    out.append(
        Insight(
            "gross_margin",
            "pnl",
            f"Gross margin {_pct(snap.fy.gm_pct)}. YTD profit (sales - COGS - operating expenses) {_inr(snap.ytd_profit)}.",
            gm_tone,
        )
    )

    if snap.series.labels:
        label = snap.series.labels[-1]
        out.append(
            Insight(
                "monthly_profit",
                "pnl",
                f"{label} profit (sales - COGS - operating expenses) {_inr(snap.monthly_profit)}.",
                "danger" if snap.monthly_profit < ZERO else "neutral",
            )
        )

    coll = snap.collection_efficiency
    coll_tone = "danger" if coll < COLLECTION_EFFICIENCY_MIN else "success"
    out.append(
        Insight(
            "collections",
            "aging",
            f"Collection efficiency (receipts / sales) {_pct(coll)}. DSO {snap.dso if snap.dso is not None else 'n/a'}.",
            coll_tone if snap.fy.sales > ZERO else "neutral",
        )
    )

    ar = snap.ar
    overdue = snap.ar_aging.get("90+", ZERO)
    if ar > ZERO:
        share = overdue / ar
        aging_tone = "danger" if share >= money("0.25") else "neutral"
        out.append(
            Insight(
                "ar_90",
                "aging",
                f"AR 90+ is {_pct(share)} of receivables ({_inr(overdue)} of {_inr(ar)}).",
                aging_tone,
            )
        )

    wc_tone = "danger" if snap.working_capital < ZERO else "neutral"
    out.append(
        Insight(
            "working_capital",
            "ceo",
            f"Operating working capital (AR + stock - AP) {_inr(snap.working_capital)}.",
            wc_tone,
        )
    )

    if snap.metrics.top_customer_share >= CUSTOMER_SHARE_MAX:
        name = snap.metrics.top_customer or "Top customer"
        out.append(
            Insight(
                "concentration",
                "ceo",
                f"{name} is {_pct(snap.metrics.top_customer_share)} of sales (policy under 35%).",
                "danger",
            )
        )

    if snap.dso is not None and snap.dso > DSO_DAYS_MAX:
        out.append(
            Insight(
                "dso",
                "aging",
                f"DSO is {snap.dso} days against a 120-day policy.",
                "danger",
            )
        )

    fc = cash_forecast(snap)
    h90 = fc.horizons[-1]
    blocked = ""
    if fc.blocked_ar > ZERO:
        blocked = f" Unscheduled AR {_inr(fc.blocked_ar)} is not timed."
    out.append(
        Insight(
            "cash_forecast",
            "cfo",
            f"Cash in 90 days {_inr(h90.cash)} if 0-90 day AR and AP convert.{blocked}",
            "danger" if h90.cash < ZERO else "neutral",
        )
    )

    benches = build_benchmarks(snap)
    breaches = [row.name for row in benches if row.policy_status == "Breach"]
    if breaches:
        out.append(
            Insight(
                "benchmarks",
                "board",
                (
                    "SSDV policy breach: "
                    + ", ".join(breaches)
                    + ". Peer is ABC trading baseline when that vault exists, not an industry average."
                ),
                "danger",
            )
        )
    else:
        out.append(
            Insight(
                "benchmarks",
                "board",
                "Listed KPIs Hold vs SSDV policy bands. Peer is ABC trading baseline, not an industry average.",
                "success",
            )
        )

    out.extend(build_why(snap))
    return tuple(out[:limit])
