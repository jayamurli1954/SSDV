from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def monthly_series(payload: dict[str, Any], series_id: str, *, last: int = 12) -> tuple[list[str], list[float]]:
    monthly = (payload.get("charts") or {}).get("monthly") or {}
    labels = list(monthly.get("categories") or [])[-last:]
    row = next((item for item in monthly.get("series") or [] if item.get("id") == series_id), None)
    data = [to_float(v) for v in (row or {}).get("data") or []][-last:]
    n = min(len(labels), len(data))
    return labels[:n], data[:n]


def aging_points(payload: dict[str, Any], key: str = "ar_aging") -> list[dict[str, Any]]:
    rows = ((payload.get("charts") or {}).get(key) or {}).get("data") or []
    return [{"label": str(row.get("label") or ""), "value": to_float(row.get("value"))} for row in rows]


def pack_tiles(payload: dict[str, Any], pack_id: str) -> list[dict[str, Any]]:
    pack = next((item for item in payload.get("packs") or [] if item.get("id") == pack_id), None)
    return list((pack or {}).get("tiles") or [])


def kpi_points(payload: dict[str, Any], keys: list[tuple[str, str]]) -> list[dict[str, Any]]:
    kpis = payload.get("kpis") or {}
    return [{"label": name, "value": to_float(kpis.get(key))} for key, name in keys]


def scorecard_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("scorecard") or []
    return [
        {
            "name": str(row.get("name") or ""),
            "actual": str(row.get("actual") or ""),
            "status": str(row.get("status") or ""),
            "tone": str(row.get("tone") or "neutral"),
        }
        for row in rows
    ]


def pnl_mix_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    mix = ((payload.get("charts") or {}).get("pnl_mix") or {}).get("data") or []
    return [{"label": str(row.get("label") or ""), "value": to_float(row.get("value"))} for row in mix]


def monthly_profit_points(payload: dict[str, Any]) -> tuple[list[str], list[float]]:
    labels, sales = monthly_series(payload, "sales")
    _, cogs = monthly_series(payload, "cogs")
    _, opex = monthly_series(payload, "opex")
    n = min(len(labels), len(sales), len(cogs), len(opex))
    profit = [sales[i] - cogs[i] - opex[i] for i in range(n)]
    return labels[:n], profit
