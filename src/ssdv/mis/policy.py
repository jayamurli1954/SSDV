"""Alert thresholds. Defaults suit a trading business; each client book can override
them in ``<vault-stem>.thresholds.yaml`` so a 90-day-credit distributor and a cash
retailer are not judged by the same limits.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from ssdv.money import money

CUSTOMER_SHARE_MAX = money("0.35")
VENDOR_SHARE_MAX = money("0.55")
DSO_DAYS_MAX = 120
INVENTORY_TO_SALES_MAX = money("0.45")
COGS_RATIO_MAX = money("0.84")
AR_TO_SALES_STRESS = money("0.30")
COLLECTION_EFFICIENCY_MIN = money("0.80")

PACK_IDS = ("ceo", "cfo", "board", "all")


@dataclass(frozen=True)
class ClientPolicy:
    customer_share_max: Decimal = CUSTOMER_SHARE_MAX
    vendor_share_max: Decimal = VENDOR_SHARE_MAX
    dso_days_max: int = DSO_DAYS_MAX
    inventory_to_sales_max: Decimal = INVENTORY_TO_SALES_MAX
    cogs_ratio_max: Decimal = COGS_RATIO_MAX
    ar_to_sales_stress: Decimal = AR_TO_SALES_STRESS
    collection_efficiency_min: Decimal = COLLECTION_EFFICIENCY_MIN
    runway_red_months: Decimal = Decimal(3)
    runway_amber_months: Decimal = Decimal(6)


DEFAULT_POLICY = ClientPolicy()

# (field, label, unit, min, max). Ratios are entered as percentages.
THRESHOLD_FIELDS: tuple[tuple[str, str, str, float, float], ...] = (
    ("dso_days_max", "DSO limit", "days", 1, 720),
    ("collection_efficiency_min", "Collections at least", "% of sales", 1, 100),
    ("customer_share_max", "Top customer under", "% of sales", 1, 100),
    ("vendor_share_max", "Top vendor under", "% of purchases", 1, 100),
    ("cogs_ratio_max", "COGS under", "% of sales", 1, 100),
    ("inventory_to_sales_max", "Inventory under", "% of sales", 1, 500),
    ("ar_to_sales_stress", "Receivables stress above", "% of sales", 1, 500),
    ("runway_red_months", "Runway red below", "months", 0, 60),
    ("runway_amber_months", "Runway amber below", "months", 0, 60),
)
_RATIO_FIELDS = {
    "collection_efficiency_min",
    "customer_share_max",
    "vendor_share_max",
    "cogs_ratio_max",
    "inventory_to_sales_max",
    "ar_to_sales_stress",
}


class PolicyError(ValueError):
    """A threshold file or entry is not usable."""


def policy_of(snap: Any) -> ClientPolicy:
    return getattr(snap, "policy", None) or DEFAULT_POLICY


def thresholds_path(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.stem}.thresholds.yaml")


def _coerce(name: str, raw: Any, *, percent: bool) -> Decimal | int:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise PolicyError(f"Threshold {name} must be a number, not {raw!r}") from exc
    spec = next(item for item in THRESHOLD_FIELDS if item[0] == name)
    low, high = Decimal(str(spec[3])), Decimal(str(spec[4]))
    if name in _RATIO_FIELDS and not percent and value <= Decimal(5):
        value = value * 100  # file may hold 0.35 or 35
    if not low <= value <= high:
        raise PolicyError(f"{spec[1]} must be between {spec[3]} and {spec[4]} {spec[2]}")
    if name == "dso_days_max":
        return int(value)
    if name in _RATIO_FIELDS:
        return money(value / 100)
    return value.quantize(Decimal("0.1"))


def build_policy(values: dict[str, Any], *, percent: bool = False) -> ClientPolicy:
    known = {f.name for f in fields(ClientPolicy)}
    unknown = sorted(set(values) - known)
    if unknown:
        raise PolicyError(f"Unknown threshold(s): {', '.join(unknown)}")
    changes = {
        name: _coerce(name, raw, percent=percent)
        for name, raw in values.items()
        if raw is not None and raw != ""
    }
    policy = replace(DEFAULT_POLICY, **changes)
    if policy.runway_red_months > policy.runway_amber_months:
        raise PolicyError("Runway red limit cannot be above the amber limit")
    return policy


def load_policy(db_path: Path | None) -> ClientPolicy:
    if db_path is None:
        return DEFAULT_POLICY
    path = thresholds_path(db_path)
    if not path.is_file():
        return DEFAULT_POLICY
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise PolicyError(f"{path.name} must be a mapping of threshold: value")
    return build_policy(raw)


def changed_from_default(policy: ClientPolicy) -> dict[str, Any]:
    base = asdict(DEFAULT_POLICY)
    return {k: v for k, v in asdict(policy).items() if v != base[k]}


def save_policy(db_path: Path, policy: ClientPolicy) -> Path | None:
    """Write only the thresholds that differ from the defaults; remove the file if none."""
    path = thresholds_path(db_path)
    changed = changed_from_default(policy)
    if not changed:
        path.unlink(missing_ok=True)
        return None
    body = {
        k: (int(v) if k == "dso_days_max" else float(v * 100) if k in _RATIO_FIELDS else float(v))
        for k, v in changed.items()
    }
    header = "# Alert thresholds for this client book. Percentages for ratios; others in days / months.\n"
    path.write_text(header + yaml.safe_dump(body, sort_keys=True), encoding="utf-8")
    return path


def display_value(policy: ClientPolicy, name: str) -> float:
    value = getattr(policy, name)
    return float(value * 100) if name in _RATIO_FIELDS else float(value)


def scorecard_rows(policy: ClientPolicy) -> tuple[tuple[str, str, str, Decimal], ...]:
    pct = lambda v: f"{v * 100:.0f}%"
    return (
        ("customer_concentration", "Customer concentration", f"Top customer < {pct(policy.customer_share_max)}", policy.customer_share_max),
        ("vendor_dependency", "Vendor dependency", f"Top vendor < {pct(policy.vendor_share_max)}", policy.vendor_share_max),
        ("collections", "Collections", f"DSO <= {policy.dso_days_max} days", Decimal(policy.dso_days_max)),
        ("stock", "Stock", f"Inventory / sales < {policy.inventory_to_sales_max:.2f}", policy.inventory_to_sales_max),
        ("gross_margin", "Gross margin", f"COGS / sales < {policy.cogs_ratio_max:.2f}", policy.cogs_ratio_max),
        ("solvency", "Solvency", "Equity >= 0 after close", money("0")),
    )


SCORECARD = scorecard_rows(DEFAULT_POLICY)
