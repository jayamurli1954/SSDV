from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from ssdv.mis.kpis import MisSnapshot, PeriodPnl
from ssdv.mis.packs import MisPack, build_pack, scorecard
from ssdv.mis.series import MonthlySeries
from ssdv.scenarios.metrics import ScenarioMetrics


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        if abs(value) >= Decimal(1) or value == 0:
            return f"{value:.2f}"
        return f"{value:.4f}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, ScenarioMetrics):
        return {k: _json_ready(v) for k, v in asdict(value).items()}
    if isinstance(value, PeriodPnl):
        return {k: _json_ready(v) for k, v in asdict(value).items()}
    if isinstance(value, MonthlySeries):
        return {k: _json_ready(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    return value


def snapshot_payload(snap: MisSnapshot, pack_id: str) -> dict[str, Any]:
    from ssdv.officemitra.insights import build_insights

    packs = ["ceo", "cfo", "board"] if pack_id == "all" else [pack_id]
    built = [build_pack(snap, pid) for pid in packs]
    return {
        "as_of": snap.as_of.isoformat(),
        "scenario": snap.scenario_id,
        "title": snap.title,
        "known_cause": snap.known_cause,
        "golden": snap.golden,
        "company": snap.company_name,
        "pack": pack_id,
        "kpis": {
            "sales": _json_ready(snap.fy.sales),
            "cogs": _json_ready(snap.fy.cogs),
            "gross_margin": _json_ready(snap.fy.gross_margin),
            "gm_pct": _json_ready(snap.fy.gm_pct),
            "opex": _json_ready(snap.fy.opex),
            "purchases": _json_ready(snap.fy.purchases),
            "receipts": _json_ready(snap.fy.receipts),
            "payments": _json_ready(snap.fy.payments),
            "plan": _json_ready(snap.fy.plan),
            "sales_growth": _json_ready(snap.sales_growth),
            "ar": _json_ready(snap.ar),
            "ap": _json_ready(snap.ap),
            "inventory": _json_ready(snap.inventory),
            "cash": _json_ready(snap.cash),
            "hdfc": _json_ready(snap.hdfc),
            "icici": _json_ready(snap.icici),
            "od": _json_ready(snap.od),
            "od_limit": _json_ready(snap.od_limit),
            "od_utilisation": _json_ready(snap.od_utilisation),
            "gst_payable": _json_ready(snap.gst_payable),
            "salary_payable": _json_ready(snap.salary_payable),
            "term_loan": _json_ready(snap.term_loan),
            "equity": _json_ready(snap.equity),
            "assets": _json_ready(snap.equation.assets),
            "liabilities": _json_ready(snap.equation.liabilities),
            "dso": snap.dso,
            "dio": snap.dio,
            "dpo": snap.dpo,
            "ccc": snap.ccc,
            "ar_aging": _json_ready(snap.ar_aging),
            "ap_aging": _json_ready(snap.ap_aging),
            "top_customer": snap.metrics.top_customer,
            "top_customer_share": _json_ready(snap.metrics.top_customer_share),
            "top_vendor": snap.metrics.top_vendor,
            "top_vendor_share": _json_ready(snap.metrics.top_vendor_share),
            "ar_to_sales": _json_ready(snap.metrics.ar_to_sales),
            "inventory_to_sales": _json_ready(snap.metrics.inventory_to_sales),
            "cogs_ratio": _json_ready(snap.metrics.cogs_ratio),
            "working_capital": _json_ready(snap.working_capital),
            "collection_efficiency": _json_ready(snap.collection_efficiency),
            "ytd_profit": _json_ready(snap.ytd_profit),
            "monthly_profit": _json_ready(snap.monthly_profit),
            "equation_holds": snap.equation.holds,
            "signal_ok": snap.signal_ok,
            "signal_detail": snap.signal_detail,
        },
        "fy": _json_ready(snap.fy),
        "prior": _json_ready(snap.prior),
        "series": _json_ready(snap.series),
        "charts": _charts_payload(snap),
        "insights": [
            {
                "id": item.id,
                "surface": item.surface,
                "text": item.text,
                "tone": item.tone,
            }
            for item in build_insights(snap)
        ],
        "scorecard": [
            {
                "id": row.id,
                "name": row.name,
                "policy": row.policy,
                "actual": row.actual,
                "status": row.status,
                "tone": row.tone,
            }
            for row in scorecard(snap)
        ],
        "packs": [_pack_payload(pack) for pack in built],
    }


def _named_series(series_id: str, name: str, data: Any) -> dict[str, Any]:
    return {"id": series_id, "name": name, "data": _json_ready(data)}


def _aging_chart(kind: str, aging: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "doughnut",
        "id": kind,
        "data": [{"label": label, "value": _json_ready(value)} for label, value in aging.items()],
    }


def _charts_payload(snap: MisSnapshot) -> dict[str, Any]:
    monthly = snap.series
    pnl_mix = [
        {"label": "COGS", "value": _json_ready(snap.fy.cogs)},
        {"label": "Gross margin", "value": _json_ready(snap.fy.gross_margin)},
    ]
    return {
        "monthly": {
            "type": "line",
            "grain": monthly.grain,
            "categories": list(monthly.labels),
            "keys": list(monthly.categories),
            "series": [
                _named_series("sales", "Taxable sales", monthly.sales),
                _named_series("cogs", "COGS", monthly.cogs),
                _named_series("gross_margin", "Gross margin", monthly.gross_margin),
                _named_series("purchases", "Purchases (inventory)", monthly.purchases),
                _named_series("receipts", "Receipts", monthly.receipts),
                _named_series("payments", "Vendor payments", monthly.payments),
                _named_series("opex", "Opex (ex-COGS)", monthly.opex),
            ],
        },
        "ar_aging": _aging_chart("ar_aging", snap.ar_aging),
        "ap_aging": _aging_chart("ap_aging", snap.ap_aging),
        "pnl_mix": {"type": "pie", "id": "pnl_mix", "data": pnl_mix},
    }


def _pack_payload(pack: MisPack) -> dict[str, Any]:
    return {
        "id": pack.id,
        "title": pack.title,
        "tiles": [
            {
                "id": tile.id,
                "label": tile.label,
                "value": tile.value,
                "tone": tile.tone,
                "drill": tile.drill,
            }
            for tile in pack.tiles
        ],
        "notes": list(pack.notes),
        "scorecard": [
            {
                "id": row.id,
                "name": row.name,
                "policy": row.policy,
                "actual": row.actual,
                "status": row.status,
                "tone": row.tone,
            }
            for row in pack.scorecard
        ],
    }


def dumps_snapshot(snap: MisSnapshot, pack_id: str) -> str:
    return json.dumps(snapshot_payload(snap, pack_id), indent=2)


def render_pack(snap: MisSnapshot, pack: MisPack) -> list[str]:
    lines = [
        f"{snap.company_name}",
        f"{pack.title}  {snap.scenario_id}  as of {snap.as_of.isoformat()}  {snap.fy.fy_code} YTD",
        f"Cause: {snap.known_cause}",
        "",
    ]
    if pack.id == "ceo":
        from ssdv.officemitra.insights import build_insights

        lines.append("  OfficeMitra")
        for item in build_insights(snap):
            lines.append(f"  [{item.surface}] {item.text}")
        lines.append("")
    for tile in pack.tiles:
        lines.append(f"  {tile.label:<28} {tile.value:>20}")
    if pack.scorecard:
        lines.append("")
        lines.append("  Scorecard")
        lines.append(f"  {'Policy':<28} {'Actual':>16}  {'Status':<8}  Rule")
        for row in pack.scorecard:
            lines.append(f"  {row.name:<28} {row.actual:>16}  {row.status:<8}  {row.policy}")
    lines.append("")
    lines.extend(pack.notes)
    return lines


def render_mis(snap: MisSnapshot, pack_id: str) -> str:
    packs = ["ceo", "cfo", "board"] if pack_id == "all" else [pack_id]
    blocks = [render_pack(snap, build_pack(snap, pid)) for pid in packs]
    sep = ["", "-" * 72, ""]
    out: list[str] = []
    for i, block in enumerate(blocks):
        if i:
            out.extend(sep)
        out.extend(block)
    return "\n".join(out)
