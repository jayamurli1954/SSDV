"""OfficeMitra license loading and plan feature gates."""

from ssdv.licensing.license import (
    License,
    LicenseError,
    license_status,
    load_license,
    parse_license_payload,
    resolve_license_paths,
)
from ssdv.licensing.plans import PlanSpec, feature_allowed, load_plans, plan_for

__all__ = [
    "License",
    "LicenseError",
    "PlanSpec",
    "feature_allowed",
    "license_status",
    "load_license",
    "load_plans",
    "parse_license_payload",
    "plan_for",
    "resolve_license_paths",
]
