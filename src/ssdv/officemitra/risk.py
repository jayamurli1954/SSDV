"""Red / amber / green client triage for the firm roster. Deterministic; no LLM math.

The band is the worst of two signals already computed from posted journals: the
board red flags (``build_red_flags``) and the cash runway (``ssdv.mis.runway``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ssdv.mis.policy import ClientPolicy, policy_of
from ssdv.mis.runway import RunwayBase, runway_base, runway_text
from ssdv.officemitra.insights import build_red_flags

RED = "red"
AMBER = "amber"
GREEN = "green"
RISK_ORDER = {RED: 0, AMBER: 1, GREEN: 2}
NO_ALERT = "No board exceptions."


@dataclass(frozen=True)
class RiskAssessment:
    band: str
    reasons: tuple[str, ...]
    base: RunwayBase

    @property
    def runway(self) -> Decimal | None:
        return self.base.runway

    @property
    def top_alert(self) -> str:
        return self.reasons[0] if self.reasons else NO_ALERT


def _months(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _worse(current: str, candidate: str) -> str:
    return candidate if RISK_ORDER[candidate] < RISK_ORDER[current] else current


def assess_risk(snap: Any, policy: ClientPolicy | None = None) -> RiskAssessment:
    policy = policy or policy_of(snap)
    base = runway_base(snap)
    band = GREEN
    reasons: list[str] = []
    runway = base.runway
    if runway is not None:
        text = f"Cash runway is {runway_text(runway)} at the current burn"
        if runway <= 0:
            band = RED
            reasons.append(
                f"No cash runway: cash is not positive and the books burn "
                f"{base.burn:,.2f} a month."
            )
        elif runway < policy.runway_red_months:
            band = RED
            reasons.append(f"{text} (below {_months(policy.runway_red_months)} months).")
        elif runway < policy.runway_amber_months:
            band = AMBER
            reasons.append(f"{text} (below {_months(policy.runway_amber_months)} months).")
    for flag in build_red_flags(snap):
        if flag.tone == "danger":
            band = _worse(band, RED)
        elif flag.tone == "warning":
            band = _worse(band, AMBER)
        else:
            continue
        reasons.append(flag.text)
    return RiskAssessment(band=band, reasons=tuple(reasons), base=base)
