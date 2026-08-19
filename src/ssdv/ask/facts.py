from __future__ import annotations

from typing import Any

from ssdv.mis.format import snapshot_payload
from ssdv.mis.kpis import MisSnapshot


def _tail(values: list[Any], n: int) -> list[Any]:
    if n <= 0:
        return []
    if len(values) <= n:
        return list(values)
    return list(values[-n:])


def compact_facts(payload: dict[str, Any], *, months: int = 12) -> dict[str, Any]:
    """Shrink MIS JSON to the slice an LLM should see. No extra narrative."""
    series = payload.get("series") or {}
    categories = list(series.get("categories") or [])
    labels = list(series.get("labels") or [])
    keep = min(months, len(categories)) if categories else 0
    monthly = {
        "grain": series.get("grain", "month"),
        "categories": _tail(categories, keep),
        "labels": _tail(labels, keep),
        "sales": _tail(list(series.get("sales") or []), keep),
        "cogs": _tail(list(series.get("cogs") or []), keep),
        "gross_margin": _tail(list(series.get("gross_margin") or []), keep),
        "purchases": _tail(list(series.get("purchases") or []), keep),
        "receipts": _tail(list(series.get("receipts") or []), keep),
        "payments": _tail(list(series.get("payments") or []), keep),
        "opex": _tail(list(series.get("opex") or []), keep),
    }
    scenario = str(payload.get("scenario") or "")
    planted = scenario not in {"imported", ""}
    facts: dict[str, Any] = {
        "company": payload.get("company"),
        "as_of": payload.get("as_of"),
        "scenario": scenario,
        "planted_ssdv_seed": planted,
        "kpis": payload.get("kpis") or {},
        "fy": payload.get("fy"),
        "prior": payload.get("prior"),
        "scorecard": payload.get("scorecard") or [],
        "red_flags": payload.get("red_flags") or [],
        "why_notes": [
            item for item in payload.get("insights") or [] if item.get("surface") == "why"
        ],
        "cash_forecast": payload.get("cash_forecast") or {},
        "benchmarks": payload.get("benchmarks") or [],
        "benchmark_source": payload.get("benchmark_source") or "",
        "whatif": payload.get("whatif") or [],
        "whatif_method": payload.get("whatif_method") or "",
        "parties": payload.get("parties") or {},
        "monthly": monthly,
        "ar_aging": (payload.get("charts") or {}).get("ar_aging"),
        "ap_aging": (payload.get("charts") or {}).get("ap_aging"),
        "pnl_mix": (payload.get("charts") or {}).get("pnl_mix"),
    }
    if planted:
        facts["ssdv_known_cause"] = payload.get("known_cause")
        facts["ssdv_golden"] = payload.get("golden")
    return facts


def facts_from_snapshot(snap: MisSnapshot, *, months: int = 12) -> dict[str, Any]:
    peer = None
    if snap.scenario_id != "baseline":
        from ssdv.mis.benchmarks import load_baseline_peer

        peer = load_baseline_peer(snap.as_of)
    return compact_facts(snapshot_payload(snap, "all", peer=peer), months=months)
