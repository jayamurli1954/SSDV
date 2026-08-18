from __future__ import annotations

import html
from typing import Any


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _bar_row(label: str, value: float, max_value: float) -> str:
    width = 0 if max_value <= 0 else min(100, round(100 * max(value, 0) / max_value))
    return (
        f'<div class="bar-row"><span class="bar-lab">{_esc(label)}</span>'
        f'<span class="bar-track"><span class="bar-fill" style="width:{width}%"></span></span>'
        f'<span class="bar-val">{value:,.2f}</span></div>'
    )


def render_dashboard(payload: dict[str, Any]) -> str:
    """Single-file CEO screen. No CDN. Opens in a browser."""
    kpis = payload.get("kpis") or {}
    insights = payload.get("insights") or []
    ceo = next((p for p in payload.get("packs") or [] if p.get("id") == "ceo"), None)
    tiles = (ceo or {}).get("tiles") or []
    monthly = (payload.get("charts") or {}).get("monthly") or {}
    labels = list(monthly.get("categories") or [])[-12:]
    sales_series = next(
        (s for s in monthly.get("series") or [] if s.get("id") == "sales"),
        {"data": []},
    )
    sales = [float(v) for v in (sales_series.get("data") or [])[-12:]]
    max_sales = max(sales) if sales else 0.0
    bars = "".join(_bar_row(lab, val, max_sales) for lab, val in zip(labels, sales, strict=False))
    aging = ((payload.get("charts") or {}).get("ar_aging") or {}).get("data") or []
    aging_rows = "".join(
        f"<tr><td>{_esc(row.get('label'))}</td><td class='num'>{_esc(row.get('value'))}</td></tr>"
        for row in aging
    )
    insight_html = "".join(
        f'<p class="insight tone-{_esc(item.get("tone") or "neutral")}">'
        f'<span class="surface">{_esc(item.get("surface"))}</span> {_esc(item.get("text"))}</p>'
        for item in insights
    )
    tile_html = "".join(
        f'<div class="tile tone-{_esc(t.get("tone") or "neutral")}">'
        f'<div class="tile-val">{_esc(t.get("value"))}</div>'
        f'<div class="tile-lab">{_esc(t.get("label"))}</div></div>'
        for t in tiles
    )
    analyst = payload.get("analyst")
    analyst_block = ""
    if analyst:
        analyst_block = f'<section class="card"><h2>OfficeMitra (Ollama)</h2><p>{_esc(analyst)}</p></section>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>OfficeMitra CEO dashboard</title>
<style>
body {{ font-family: Segoe UI, sans-serif; margin: 24px; color: #1a1a1a; background: #f4f4f4; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
h2 {{ font-size: 15px; margin: 0 0 12px; }}
.meta {{ color: #555; margin-bottom: 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }}
.tile {{ background: #fff; padding: 12px; border: 1px solid #ddd; }}
.tile-val {{ font-size: 18px; font-weight: 600; }}
.tile-lab {{ font-size: 12px; color: #555; margin-top: 4px; }}
.tone-danger .tile-val, .insight.tone-danger {{ color: #8b1e1e; }}
.tone-success .tile-val, .insight.tone-success {{ color: #1e5a32; }}
.tone-warning .tile-val, .insight.tone-warning {{ color: #8a5a00; }}
.card {{ background: #fff; border: 1px solid #ddd; padding: 16px; margin-top: 16px; }}
.insight {{ margin: 0 0 8px; }}
.surface {{ display: inline-block; font-size: 11px; color: #666; text-transform: uppercase; margin-right: 6px; }}
.bar-row {{ display: grid; grid-template-columns: 72px 1fr 110px; gap: 8px; align-items: center; margin: 4px 0; font-size: 12px; }}
.bar-track {{ background: #e6e6e6; height: 10px; }}
.bar-fill {{ display: block; height: 10px; background: #2f5d8a; }}
.bar-val, .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
td, th {{ border-bottom: 1px solid #eee; padding: 6px 0; }}
.cols {{ display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }}
</style>
</head>
<body>
<h1>{_esc(payload.get("company"))}</h1>
<p class="meta">OfficeMitra CEO screen · {_esc(payload.get("scenario"))} · as of {_esc(payload.get("as_of"))} · WC {_esc(kpis.get("working_capital"))} · collections {_esc(kpis.get("collection_efficiency"))}</p>
<div class="grid">{tile_html}</div>
<section class="card">
<h2>OfficeMitra (on this screen)</h2>
{insight_html or "<p>No insight lines.</p>"}
</section>
{analyst_block}
<div class="cols">
<section class="card">
<h2>Taxable sales by month</h2>
{bars or "<p>No monthly series.</p>"}
<p class="meta">Source: charts.monthly sales · last 12 months in JSON</p>
</section>
<section class="card">
<h2>AR aging</h2>
<table><thead><tr><th>Bucket</th><th class="num">INR</th></tr></thead><tbody>{aging_rows}</tbody></table>
</section>
</div>
</body>
</html>
"""
