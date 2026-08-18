from __future__ import annotations

from dataclasses import dataclass

from ssdv.mis.kpis import MisSnapshot
from ssdv.mis.policy import (
    COGS_RATIO_MAX,
    COLLECTION_EFFICIENCY_MIN,
    CUSTOMER_SHARE_MAX,
    DSO_DAYS_MAX,
)
from ssdv.money import ZERO, money


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


def build_insights(snap: MisSnapshot, *, limit: int = 8) -> tuple[Insight, ...]:
    """Short lines to show on P&L / aging / CEO. Numbers only, no invented cause."""
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

    return tuple(out[:limit])
