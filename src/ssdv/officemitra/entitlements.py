"""What this copy of OfficeMitra may do: licensed plan, free trial, or developer mode.

* A valid signed licence -> that plan's features and company limit.
* Installed app (PyInstaller build) with no valid licence -> the ``trial`` plan
  (1 client, Professional features).
* Running from source (developers, tests) with no licence -> everything, no limit.
  Set OFFICEMITRA_FORCE_TRIAL=1 to see the installed-app behaviour from source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ssdv.licensing import License, license_status, plan_for
from ssdv.paths import is_frozen

TRIAL_PLAN_ID = "trial"


@dataclass(frozen=True)
class Entitlements:
    mode: str  # "licensed" | "trial" | "developer"
    plan_name: str
    company_limit: int | None
    features: dict[str, bool]
    license: License | None = None
    problem: str | None = None

    def allows(self, feature: str) -> bool:
        if self.mode == "developer":
            return True
        return bool(self.features.get(feature, False))

    @property
    def plan_id(self) -> str | None:
        if self.license is not None:
            return self.license.plan_id
        return TRIAL_PLAN_ID if self.mode == "trial" else None

    def status_line(self) -> str:
        if self.mode == "licensed" and self.license is not None:
            return self.license.summary_line()
        if self.mode == "trial":
            return f"Free trial: {self.company_limit} client, {self.plan_name} features"
        return "Developer mode: all features, no client limit"


def _trial_mode() -> bool:
    return is_frozen() or os.environ.get("OFFICEMITRA_FORCE_TRIAL", "").strip() == "1"


def current_entitlements() -> Entitlements:
    license_obj, problem = license_status()
    if license_obj is not None:
        plan = license_obj.plan()
        features = dict(plan.features)
        if license_obj.feature_overrides:
            features.update(license_obj.feature_overrides)
        return Entitlements(
            mode="licensed",
            plan_name=plan.name,
            company_limit=int(license_obj.company_limit),
            features=features,
            license=license_obj,
        )
    if _trial_mode():
        trial = plan_for(TRIAL_PLAN_ID)
        return Entitlements(
            mode="trial",
            plan_name=trial.name,
            company_limit=trial.company_limit,
            features=dict(trial.features),
            problem=problem,
        )
    return Entitlements(mode="developer", plan_name="Developer", company_limit=None, features={}, problem=problem)


def feature_label(feature: str) -> str:
    return {
        "cfo_pack": "CFO pack",
        "board_pack": "Board pack",
        "chart_pack": "Chart pack",
        "whatif": "What-if and runway sandbox",
        "parties_intel": "Customer and supplier intelligence",
        "benchmarks": "Industry benchmarks",
        "budget_variance": "Budget vs actual",
        "alert_thresholds": "Per-client alert thresholds",
        "partner_approval": "Partner approval",
        "export_excel_ppt": "Excel and PowerPoint export",
        "ask_why": "Ask why",
        "connect_tally_xml": "Tally XML import",
        "connect_tally_http": "Live Tally connection",
    }.get(feature, feature)


def upgrade_note(feature: str, ent: Entitlements) -> str:
    where = "your free trial" if ent.mode == "trial" else f"the {ent.plan_name} plan"
    return (
        f"{feature_label(feature)} is not included in {where}. "
        "Contact SanMitra (www.sanmitratech.in) to upgrade."
    )
