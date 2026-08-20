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


def _party_rows(rows: list[dict[str, Any]], overdue_label: str) -> str:
    return "".join(
        f"<tr><td>{_esc(row.get('name'))}</td>"
        f"<td class='num'>{_esc(row.get(overdue_label))}</td>"
        f"<td class='num'>{_esc(row.get('outstanding'))}</td>"
        f"<td class='num'>{_esc(row.get('unaged'))}</td>"
        f"<td>{_esc(row.get('oldest_days') if row.get('oldest_days') is not None else 'unaged')}</td></tr>"
        for row in rows
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
    fc = payload.get("cash_forecast") or {}
    forecast_rows = "".join(
        f"<tr><td>{_esc(row.get('label'))}</td>"
        f"<td class='num'>{_esc(row.get('ar_in'))}</td>"
        f"<td class='num'>{_esc(row.get('ap_out'))}</td>"
        f"<td class='num'>{_esc(row.get('cash'))}</td></tr>"
        for row in fc.get("horizons") or []
    )
    forecast_block = (
        (
            f'<section class="card"><h2>Cash forecast (open AR/AP)</h2>'
            f'<p class="meta">{_esc(fc.get("method") or "")}</p>'
            f"<table><thead><tr><th>Horizon</th><th class='num'>AR in</th>"
            f"<th class='num'>AP out</th><th class='num'>Cash</th></tr></thead>"
            f"<tbody>{forecast_rows}</tbody></table></section>"
        )
        if forecast_rows
        else ""
    )
    insight_html = "".join(
        f'<p class="insight tone-{_esc(item.get("tone") or "neutral")}">'
        f'<span class="surface">{_esc(item.get("surface"))}</span> {_esc(item.get("text"))}</p>'
        for item in insights
        if item.get("surface") != "why"
    )
    why_html = "".join(
        f'<p class="insight tone-{_esc(item.get("tone") or "neutral")}">'
        f'<span class="surface">why</span> {_esc(item.get("text"))}</p>'
        for item in insights
        if item.get("surface") == "why"
    )
    flag_html = "".join(
        f'<p class="insight tone-{_esc(item.get("tone") or "danger")}">'
        f'<span class="surface">flag</span> {_esc(item.get("text"))}</p>'
        for item in payload.get("red_flags") or []
    )
    bench_rows = "".join(
        f"<tr><td>{_esc(row.get('name'))}</td>"
        f"<td class='num'>{_esc(row.get('actual'))}</td>"
        f"<td>{_esc(row.get('policy'))}</td>"
        f"<td>{_esc(row.get('policy_status'))}</td>"
        f"<td class='num'>{_esc(row.get('peer'))}</td>"
        f"<td>{_esc(row.get('vs_peer'))}</td></tr>"
        for row in payload.get("benchmarks") or []
    )
    bench_block = (
        (
            f'<section class="card"><h2>Benchmarks</h2>'
            f'<p class="meta">{_esc(payload.get("benchmark_source") or "")}</p>'
            f"<table><thead><tr><th>KPI</th><th class='num'>Actual</th><th>SSDV policy</th>"
            f"<th>Policy</th><th class='num'>ABC baseline</th><th>vs ABC</th></tr></thead>"
            f"<tbody>{bench_rows}</tbody></table></section>"
        )
        if bench_rows
        else ""
    )
    whatif_rows = "".join(
        f"<tr><td>{_esc(row.get('prompt'))}</td>"
        f"<td>{_esc(row.get('result'))}</td>"
        f"<td class='num'>{_esc(row.get('delta_inr'))}</td></tr>"
        for row in payload.get("whatif") or []
    )
    whatif_block = (
        (
            f'<section class="card"><h2>What-if (recommend-only)</h2>'
            f'<p class="meta">{_esc(payload.get("whatif_method") or "")}</p>'
            f"<table><thead><tr><th>Scenario</th><th>Result</th><th class='num'>Delta INR</th>"
            f"</tr></thead><tbody>{whatif_rows}</tbody></table></section>"
        )
        if whatif_rows
        else ""
    )
    parties = payload.get("parties") or {}
    overdue_rows = _party_rows(list(parties.get("overdue_customers") or []), "overdue_90")
    vendor_rows = _party_rows(list(parties.get("vendor_exposure") or []), "overdue_90")
    party_block = ""
    if overdue_rows or vendor_rows:
        party_block = (
            f'<section class="card"><h2>Customer & vendor intelligence</h2>'
            f'<p class="meta">{_esc(parties.get("method") or "")}</p>'
            f"<h2>Top overdue customers</h2>"
            f"<table><thead><tr><th>Customer</th><th class='num'>AR 90+</th>"
            f"<th class='num'>Outstanding</th><th class='num'>Unaged</th><th>Oldest</th></tr></thead>"
            f"<tbody>{overdue_rows or '<tr><td colspan=5>None</td></tr>'}</tbody></table>"
            f"<h2>Top vendor exposure</h2>"
            f"<table><thead><tr><th>Vendor</th><th class='num'>AP 90+</th>"
            f"<th class='num'>Outstanding</th><th class='num'>Unaged</th><th>Oldest</th></tr></thead>"
            f"<tbody>{vendor_rows or '<tr><td colspan=5>None</td></tr>'}</tbody></table></section>"
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
        analyst_block = (
            f'<section class="card"><h2>OfficeMitra (Ollama)</h2><p>{_esc(analyst)}</p></section>'
        )
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
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
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
<section class="card">
<h2>Why (from posted books)</h2>
{why_html or "<p>No month-on-month driver isolated from these journals.</p>"}
</section>
<section class="card">
<h2>Board red flags</h2>
{flag_html or "<p>No Board red flags on DSO policy, cash, equity, or last-month profit.</p>"}
</section>
{bench_block}
{whatif_block}
{party_block}
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
{forecast_block}
</body>
</html>
"""
