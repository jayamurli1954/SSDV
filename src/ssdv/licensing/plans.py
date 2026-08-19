from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ssdv.paths import load_yaml, repo_root


@dataclass(frozen=True)
class PlanSpec:
    id: str
    name: str
    company_limit: int
    price_inr: int
    amc_inr: int
    features: dict[str, bool]
    price_inr_list: int | None = None


def _plans_path() -> Path:
    return repo_root() / "config" / "licensing" / "plans.yaml"


def load_plans(path: Path | None = None) -> dict[str, PlanSpec]:
    raw = load_yaml(path or _plans_path())
    plans_raw = raw.get("plans")
    if not isinstance(plans_raw, dict):
        raise ValueError("plans.yaml must contain a 'plans' mapping")

    out: dict[str, PlanSpec] = {}
    for plan_id, spec in plans_raw.items():
        if not isinstance(spec, dict):
            continue
        features = spec.get("features") or {}
        if not isinstance(features, dict):
            raise ValueError(f"Plan {plan_id}: features must be a mapping")
        out[str(plan_id)] = PlanSpec(
            id=str(plan_id),
            name=str(spec.get("name") or plan_id),
            company_limit=int(spec["company_limit"]),
            price_inr=int(spec["price_inr"]),
            amc_inr=int(spec["amc_inr"]),
            features={str(k): bool(v) for k, v in features.items()},
            price_inr_list=int(spec["price_inr_list"]) if spec.get("price_inr_list") else None,
        )
    return out


def plan_for(plan_id: str, *, plans: dict[str, PlanSpec] | None = None) -> PlanSpec:
    catalog = plans or load_plans()
    if plan_id not in catalog:
        known = ", ".join(sorted(catalog))
        raise KeyError(f"Unknown plan_id {plan_id!r}. Choose one of: {known}")
    return catalog[plan_id]


def feature_allowed(plan_id: str, feature: str, *, plans: dict[str, PlanSpec] | None = None) -> bool:
    return plan_for(plan_id, plans=plans).features.get(feature, False)


def plans_as_dict(path: Path | None = None) -> dict[str, Any]:
    """Raw YAML for tooling / docs generation."""
    return load_yaml(path or _plans_path())
