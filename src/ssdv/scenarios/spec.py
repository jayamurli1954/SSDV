from __future__ import annotations

import copy
from typing import Any

from ssdv.paths import load_company

SCENARIO_IDS = (
    "baseline",
    "customer_concentration",
    "cash_flow_crisis",
    "inventory_buildup",
    "vendor_dependency",
    "margin_erosion",
)

_KNOBS: dict[str, dict[str, Any]] = {
    "baseline": {
        "seed_offset": 0,
        "collection_weights": [40, 35, 15, 10],
        "opening_ar_collect": 0.80,
    },
    "customer_concentration": {
        "seed_offset": 100,
        "sales_whale_share": 0.42,
        "collection_weights": [40, 35, 15, 10],
        "opening_ar_collect": 0.80,
    },
    "cash_flow_crisis": {
        "seed_offset": 200,
        "collection_weights": [8, 12, 30, 50],
        "opening_ar_collect": 0.35,
        "volumes_receipts": 2200,
        "volumes_payments": 2200,
    },
    "inventory_buildup": {
        "seed_offset": 300,
        "sales_year_weights": [1.0, 1.0, 1.0],
        "sales_flat_revenue": True,
        "purchase_qty_multipliers": [1.20, 1.40, 1.60],
        "collection_weights": [40, 35, 15, 10],
        "opening_ar_collect": 0.80,
    },
    "vendor_dependency": {
        "seed_offset": 400,
        "vendor_whale_share": 0.70,
        "collection_weights": [40, 35, 15, 10],
        "opening_ar_collect": 0.80,
    },
    "margin_erosion": {
        "seed_offset": 500,
        "cost_multipliers": [1.08, 1.18, 1.30],
        "sell_multipliers": [1.00, 1.02, 1.04],
        "collection_weights": [40, 35, 15, 10],
        "opening_ar_collect": 0.80,
    },
    "imported": {
        "seed_offset": 0,
    },
}

GOLDEN: dict[str, dict[str, str]] = {
    "baseline": {
        "title": "Healthy growth",
        "known_cause": "Sales, profit, and cash all rise",
        "golden": (
            "Baseline control set: revenue grows across FY 2023-24 to FY 2025-26, "
            "collections follow normal credit terms, and no single customer or vendor dominates. "
            "OfficeMitra should treat this as healthy growth, not a risk case."
        ),
    },
    "customer_concentration": {
        "title": "Customer concentration",
        "known_cause": "Top customer ~40% of revenue",
        "golden": (
            "Customer concentration risk: about 40% of sales revenue is with a single customer. "
            "A delay or default by that account would hit both revenue and cash."
        ),
    },
    "cash_flow_crisis": {
        "title": "Cash-flow crisis",
        "known_cause": "Sales up, DSO up, cash down",
        "golden": (
            "Collections lag: invoices keep going out but receipts are late or missing, so DSO rises "
            "and bank balances fall even when sales are growing."
        ),
    },
    "inventory_buildup": {
        "title": "Inventory buildup",
        "known_cause": "Inventory up, sales flat",
        "golden": (
            "Excess stock: purchases keep rising while sales stay flat, so inventory and working capital "
            "tied up in warehouses grow faster than revenue."
        ),
    },
    "vendor_dependency": {
        "title": "Vendor dependency",
        "known_cause": "One vendor >60% of purchases",
        "golden": (
            "Supplier concentration risk: more than 60% of purchases come from a single vendor. "
            "A disruption there would starve stock and purchases."
        ),
    },
    "margin_erosion": {
        "title": "Margin erosion",
        "known_cause": "Purchase cost up, selling price lag",
        "golden": (
            "Cost shock: purchase rates rose faster than selling prices, so COGS ate gross margin "
            "even if invoice counts still look healthy."
        ),
    },
    "imported": {
        "title": "Imported books",
        "known_cause": "External accounting system",
        "golden": (
            "Imported journals from an external accounting system. OfficeMitra should explain the "
            "measured KPIs from the posted ledger, not a planted SSDV cause."
        ),
    },
}


def scenario_ids() -> tuple[str, ...]:
    return SCENARIO_IDS


def apply_scenario(company: dict[str, Any] | None, scenario_id: str) -> dict[str, Any]:
    if scenario_id not in _KNOBS:
        known = ", ".join(SCENARIO_IDS)
        raise ValueError(f"Unknown scenario {scenario_id!r}. Choose one of: {known}")
    cfg = copy.deepcopy(company or load_company())
    knobs = dict(_KNOBS[scenario_id])
    cfg["generator"]["scenario"] = scenario_id
    cfg["generator"]["seed"] = int(cfg["generator"]["seed"]) + int(knobs.get("seed_offset", 0))
    if "volumes_receipts" in knobs:
        cfg["volumes"]["receipts"] = int(knobs["volumes_receipts"])
    if "volumes_payments" in knobs:
        cfg["volumes"]["payments"] = int(knobs["volumes_payments"])
    cfg["scenario_knobs"] = knobs
    meta = GOLDEN[scenario_id]
    cfg["scenario_meta"] = meta
    if scenario_id == "imported":
        cfg["validate_mode"] = "imported"
        for year in cfg["calendar"]["fiscal_years"]:
            year["revenue_inr"] = "0"
    return cfg


def knobs(cfg: dict[str, Any]) -> dict[str, Any]:
    return dict(
        cfg.get("scenario_knobs")
        or _KNOBS.get(str(cfg.get("generator", {}).get("scenario", "baseline")), {})
    )
