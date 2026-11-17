from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ssdv.mis.kpis import MisSnapshot
from ssdv.mis.policy import policy_of
from ssdv.money import ZERO, money


def whatif_prompts(snap=None) -> tuple[str, ...]:
    return (
        f"If DSO improves to {policy_of(snap).dso_days_max} days, how much cash is released?",
        "If YTD sales rise 15%, what is projected profit?",
        "If AR 90+ is collected, how much cash is released?",
        f"If collection efficiency reaches {policy_of(snap).collection_efficiency_min * 100:.0f}%, how much extra cash?",
    )


WHATIF_PROMPTS = whatif_prompts()

WHATIF_METHOD = (
    "Recommend-only. Each scenario scales posted YTD figures or open AR buckets. "
    "Books are not changed. No future sales plan beyond the stated lever."
)

_SALES_UP = money("0.15")


@dataclass(frozen=True)
class WhatIfRow:
    id: str
    prompt: str
    result: str
    delta_inr: Decimal | None
    tone: str
    detail: str


def _inr(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _row(
    *,
    id: str,
    prompt: str,
    result: str,
    delta_inr: Decimal | None = None,
    tone: str = "neutral",
    detail: str = "",
) -> WhatIfRow:
    return WhatIfRow(
        id=id,
        prompt=prompt,
        result=result,
        delta_inr=delta_inr,
        tone=tone,
        detail=detail or WHATIF_METHOD,
    )


def _dso_to_policy(snap: MisSnapshot) -> WhatIfRow:
    prompt = whatif_prompts(snap)[0]
    if snap.dso is None or snap.fy.sales <= ZERO:
        return _row(
            id="dso_to_120",
            prompt=prompt,
            result="DSO or YTD sales missing; this lever needs both.",
            tone="neutral",
        )
    if snap.dso <= policy_of(snap).dso_days_max:
        return _row(
            id="dso_to_120",
            prompt=prompt,
            result=f"DSO is {snap.dso} days (policy {policy_of(snap).dso_days_max}). No extra cash from this lever.",
            delta_inr=ZERO,
            tone="success",
        )
    gap = snap.dso_policy_gap_ar or ZERO
    return _row(
        id="dso_to_120",
        prompt=prompt,
        result=(
            f"DSO {snap.dso} days vs {policy_of(snap).dso_days_max}-day policy implies about {_inr(gap)} "
            f"of AR ({_inr(snap.ar)} outstanding) is above policy timing."
        ),
        delta_inr=gap,
        tone="warning" if gap > ZERO else "neutral",
        detail=f"Uses AR * (DSO - {policy_of(snap).dso_days_max}) / DSO from posted YTD sales and receivables.",
    )


def _sales_up_15(snap: MisSnapshot) -> WhatIfRow:
    prompt = whatif_prompts(snap)[1]
    sales = snap.fy.sales
    if sales <= ZERO:
        return _row(
            id="sales_up_15",
            prompt=prompt,
            result="No YTD taxable sales to scale.",
            tone="neutral",
        )
    factor = money(1) + _SALES_UP
    new_sales = money(sales * factor)
    new_cogs = money(snap.fy.cogs * factor)
    new_profit = money(new_sales - new_cogs - snap.fy.opex)
    delta = money(new_profit - snap.ytd_profit)
    return _row(
        id="sales_up_15",
        prompt=prompt,
        result=(
            f"At the same gross margin and YTD opex ({_inr(snap.fy.opex)}), "
            f"YTD profit moves from {_inr(snap.ytd_profit)} to {_inr(new_profit)} "
            f"({'+' if delta >= ZERO else ''}{_inr(delta)})."
        ),
        delta_inr=delta,
        tone="success" if delta > ZERO else "neutral",
        detail="Scales posted YTD sales and COGS by 15%; opex unchanged.",
    )


def _collect_ar90(snap: MisSnapshot) -> WhatIfRow:
    prompt = whatif_prompts(snap)[2]
    blocked = snap.cash_blocked_90
    if blocked <= ZERO:
        return _row(
            id="collect_ar90",
            prompt=prompt,
            result="No AR in the 90+ aging bucket on these books.",
            delta_inr=ZERO,
            tone="neutral",
        )
    return _row(
        id="collect_ar90",
        prompt=prompt,
        result=f"Collecting open AR 90+ ({_inr(blocked)} of {_inr(snap.ar)} receivables) releases that cash.",
        delta_inr=blocked,
        tone="warning",
        detail="Uses posted AR aging bucket 90+ only.",
    )


def _collections_to_80(snap: MisSnapshot) -> WhatIfRow:
    prompt = whatif_prompts(snap)[3]
    sales = snap.fy.sales
    if sales <= ZERO:
        return _row(
            id="collections_to_80",
            prompt=prompt,
            result="No YTD taxable sales to compare receipts against.",
            tone="neutral",
        )
    target = money(sales * policy_of(snap).collection_efficiency_min)
    extra = money(target - snap.fy.receipts)
    if extra <= ZERO:
        return _row(
            id="collections_to_80",
            prompt=prompt,
            result=(
                f"YTD receipts {_inr(snap.fy.receipts)} are already at or above "
                f"{policy_of(snap).collection_efficiency_min * 100:.0f}% of sales ({_inr(sales)})."
            ),
            delta_inr=ZERO,
            tone="success",
        )
    return _row(
        id="collections_to_80",
        prompt=prompt,
        result=(
            f"{policy_of(snap).collection_efficiency_min * 100:.0f}% of YTD sales is {_inr(target)}. Posted receipts are {_inr(snap.fy.receipts)}; "
            f"gap {_inr(extra)}."
        ),
        delta_inr=extra,
        tone="warning",
        detail="Uses YTD receipts / sales from posted journals.",
    )


def build_whatif(snap: MisSnapshot) -> tuple[WhatIfRow, ...]:
    return (
        _dso_to_policy(snap),
        _sales_up_15(snap),
        _collect_ar90(snap),
        _collections_to_80(snap),
    )
