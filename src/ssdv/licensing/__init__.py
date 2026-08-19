"""OfficeMitra license loading and plan feature gates."""

from ssdv.licensing.license import License, LicenseError, load_license, resolve_license_paths
from ssdv.licensing.plans import PlanSpec, feature_allowed, load_plans, plan_for

__all__ = [
    "License",
    "LicenseError",
    "PlanSpec",
    "feature_allowed",
    "load_license",
    "load_plans",
    "plan_for",
    "resolve_license_paths",
]
