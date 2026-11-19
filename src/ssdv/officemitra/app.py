from __future__ import annotations

import argparse
import html
from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from ssdv.ask import AskError, ask_books
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.mis.policy import PolicyError, build_policy, save_policy, thresholds_path
from ssdv.mis.runway import Levers, base_from_dict, runway_text, simulate_runway
from ssdv.money import money
from ssdv.officemitra.approval import (
    ApprovalError,
    approval_sidecar_path,
    approve,
    disable_partner_approval,
    firm_approval_path,
    set_partner_pin,
    withdraw_approval,
)
from ssdv.officemitra.boardpack import render_board_pdf
from ssdv.officemitra.branding import brand_icon_path, render_brand_header
from ssdv.officemitra.charts import (
    aging_points,
    cash_forecast_points,
    gst_points,
    kpi_points,
    monthly_profit_points,
    monthly_series,
    pack_tiles,
    pnl_mix_points,
    scorecard_points,
)
from ssdv.officemitra.dashboard import render_dashboard
from ssdv.officemitra.entitlements import Entitlements, current_entitlements, upgrade_note
from ssdv.officemitra.export import write_excel, write_ppt
from ssdv.officemitra.firm import (
    apply_company_limit,
    discover_vaults,
    effective_company_limit,
    summarize_vault,
    voucher_count,
)
from ssdv.officemitra.quality import (
    budget_sidecar_path,
    enrich_payload,
    mark_reviewed,
    review_sidecar_path,
)
from ssdv.officemitra.setup_flow import vault_has_data
from ssdv.officemitra.setup_wizard import render_setup_wizard
from ssdv.paths import default_db_path, user_data_dir

st.set_page_config(
    page_title="OfficeMitra",
    page_icon=str(brand_icon_path()) if brand_icon_path().is_file() else "📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS = """
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stMarkdownContainer"] {
  font-size: 17px !important;
  line-height: 1.5 !important;
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
}
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"], section.main {
  height: auto !important;
  max-height: none !important;
  overflow: visible !important;
}
.block-container {
  padding-top: 1.4rem !important;
  padding-bottom: 3rem !important;
  max-width: 1280px;
  overflow: visible !important;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stCaption"] {
  color: #44403C !important;
  font-size: 0.98rem !important;
  line-height: 1.45 !important;
}
h1 { letter-spacing: -0.03em; margin-bottom: 0.2rem !important; }
h2, h3 { letter-spacing: -0.02em; }
div[data-testid="stMetric"] {
  background: #fff;
  border: 1px solid #E4DCCB;
  border-radius: 12px;
  padding: 0.85rem 1rem 0.95rem;
}
div[data-testid="stMetricLabel"] p {
  color: #57534E !important;
  font-size: 0.82rem !important;
  letter-spacing: 0.02em;
}
div[data-testid="stMetricValue"] {
  font-variant-numeric: tabular-nums;
  font-size: 1.35rem !important;
  color: #1C1917 !important;
}
/* Party tables: scroll instead of clipping the last column header */
div[data-testid="stDataFrame"] {
  overflow-x: auto !important;
}
.om-note {
  border-radius: 10px;
  padding: 0.85rem 1.05rem;
  margin: 0 0 0.7rem 0;
  border: 1px solid #E4DCCB;
  background: #fff;
  color: #1C1917;
  font-size: 1.02rem;
  line-height: 1.45;
}
.om-note.success { border-left: 5px solid #2F6F4E; background: #F3F7F3; }
.om-note.warning { border-left: 5px solid #B45309; background: #FBF6EE; }
.om-note.danger { border-left: 5px solid #B42318; background: #FBF1EF; }
.om-note.neutral { border-left: 5px solid #1B4F72; background: #F3F6F8; }
.om-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1.4rem;
  color: #44403C;
  font-size: 1rem;
  margin: 0.35rem 0 1.15rem;
}
.om-meta span { font-variant-numeric: tabular-nums; }
.om-kicker {
  color: #1B4F72;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 0.15rem;
}
.om-brand-img {
  height: 58px;
  width: auto;
  display: block;
  margin: 0 0 0.35rem 0;
  padding: 0;
}
.om-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin: 0.4rem 0 1.2rem;
}
.om-tile {
  background: #fff;
  border: 1px solid #E4DCCB;
  border-radius: 12px;
  padding: 0.9rem 1rem 1rem;
  min-height: 6.2rem;
}
.om-tile-lab {
  color: #44403C;
  font-size: 0.92rem;
  line-height: 1.35;
  white-space: normal;
  overflow: visible;
}
.om-tile-val {
  margin-top: 0.4rem;
  color: #1C1917;
  font-size: 1.12rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
  white-space: normal;
  word-break: break-word;
}
</style>
"""

_UNLOCK_JS = """
<script>
(function () {
  const doc = window.parent.document;
  const sel = [
    "html", "body", ".stApp",
    "[data-testid='stAppViewContainer']",
    "[data-testid='stMain']",
    "[data-testid='stMainBlockContainer']",
    "[data-testid='stBottomBlockContainer']",
    "section.main", ".block-container"
  ];
  sel.forEach((s) => {
    doc.querySelectorAll(s).forEach((el) => {
      el.style.setProperty("height", "auto", "important");
      el.style.setProperty("max-height", "none", "important");
      el.style.setProperty("overflow", "visible", "important");
      el.style.setProperty("overflow-y", "visible", "important");
    });
  });
})();
</script>
"""


def _unlock_full_page() -> None:
    components.html(_UNLOCK_JS, height=0)


def _cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--db", default=str(default_db_path()))
    parser.add_argument("--as-of", default="2026-03-31")
    args, _rest = parser.parse_known_args()
    return args


def _inr_text(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "—")
    sign = "-" if number < 0 else ""
    whole, frac = f"{abs(number):.2f}".split(".")
    if len(whole) <= 3:
        grouped = whole
    else:
        last = whole[-3:]
        rest = whole[:-3]
        chunks: list[str] = []
        while rest:
            chunks.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join([*reversed(chunks), last])
    return f"{sign}{grouped}.{frac}"


@st.cache_data(show_spinner="Reading posted books...")
def _payload(db_path: str, as_of: str, sidecar_stamp: str = "") -> dict:
    engine = make_engine(Path(db_path))
    create_schema(engine)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, date.fromisoformat(as_of))
        peer = None
        if snap.scenario_id != "baseline":
            from ssdv.mis.benchmarks import load_baseline_peer

            peer = load_baseline_peer(snap.as_of, exclude=Path(db_path))
        payload = snapshot_payload(snap, "all", peer=peer)
        return enrich_payload(payload, session, Path(db_path), date.fromisoformat(as_of))


def _excel_bytes(payload: dict) -> bytes:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "pack.xlsx"
        write_excel(payload, path)
        return path.read_bytes()


def _ppt_bytes(payload: dict) -> bytes:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "pack.pptx"
        write_ppt(payload, path)
        return path.read_bytes()


def _sidecar_stamp(db_path: str) -> str:
    bits: list[str] = []
    for path in (
        review_sidecar_path(Path(db_path)),
        budget_sidecar_path(Path(db_path)),
        approval_sidecar_path(Path(db_path)),
        firm_approval_path(),
        thresholds_path(Path(db_path)),
    ):
        if path.is_file():
            bits.append(f"{path.name}:{path.stat().st_mtime}")
    return "|".join(bits)


@st.cache_data(show_spinner="Reading client books...")
def _firm_row(db_path: str, as_of: str, sidecar_stamp: str = "") -> dict:
    row = summarize_vault(Path(db_path), date.fromisoformat(as_of))
    return {
        "db_path": str(row.db_path),
        "vault": row.vault_label,
        "company": row.company,
        "sales": str(row.sales),
        "cash": str(row.cash),
        "ar_90": str(row.ar_90),
        "working_capital": str(row.working_capital),
        "score": "" if row.score is None else str(row.score),
        "reviewed": "approved" if row.approved else "yes" if row.reviewed else "no",
        "risk": row.risk,
        "runway": "" if row.error else runway_text(row.runway_months),
        "top_alert": row.top_alert,
        "error": row.error or "",
    }


def _note(tone: str, text: str) -> None:
    klass = tone if tone in {"danger", "warning", "success", "neutral"} else "neutral"
    st.markdown(f'<div class="om-note {klass}">{text}</div>', unsafe_allow_html=True)


def _metrics(tiles: list[dict]) -> None:
    cards = []
    for tile in tiles:
        label = html.escape(str(tile.get("label") or ""))
        value = html.escape(str(tile.get("value") or ""))
        cards.append(
            f'<div class="om-tile"><div class="om-tile-lab">{label}</div>'
            f'<div class="om-tile-val">{value}</div></div>'
        )
    st.markdown(f'<div class="om-tiles">{"".join(cards)}</div>', unsafe_allow_html=True)


def _party_oldest(row: dict) -> str:
    days = row.get("oldest_days")
    if days is None:
        return "unaged"
    return f"{days} d"


_ENT: Entitlements | None = None


def _ent() -> Entitlements:
    global _ENT
    if _ENT is None:
        _ENT = current_entitlements()
    return _ENT


def _allowed(feature: str, *, note: bool = True) -> bool:
    """True if this plan includes ``feature``; otherwise optionally show an upgrade note."""
    if _ent().allows(feature):
        return True
    if note:
        st.caption(upgrade_note(feature, _ent()))
    return False


def _render_parties(payload: dict, *, vendors: bool = True, limit: int | None = None) -> None:
    parties = payload.get("parties") or {}
    method = str(parties.get("method") or "")
    customers = list(parties.get("overdue_customers") or [])
    vendors_rows = list(parties.get("vendor_exposure") or [])
    if limit is not None:
        customers = customers[:limit]
        vendors_rows = vendors_rows[:limit]
    if not customers and not vendors_rows:
        return
    st.markdown("##### Customer & vendor intelligence")
    if method:
        st.caption(method)
    rank = str(parties.get("customer_rank") or "")
    cust_title = (
        "Top overdue customers" if rank == "overdue_90" else "Top AR balances (no 90+ aging)"
    )
    # Stack full-width: side-by-side dataframes clipped the "Oldest" column to "O".
    st.markdown(f"**{cust_title}**")
    if customers:
        st.dataframe(
            [
                {
                    "Customer": row.get("name"),
                    "AR 90+": row.get("overdue_90"),
                    "Outstanding": row.get("outstanding"),
                    "Unaged": row.get("unaged"),
                    "Oldest": _party_oldest(row),
                }
                for row in customers
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Customer": st.column_config.TextColumn("Customer", width="large"),
                "AR 90+": st.column_config.NumberColumn("AR 90+", format="%.2f"),
                "Outstanding": st.column_config.NumberColumn("Outstanding", format="%.2f"),
                "Unaged": st.column_config.NumberColumn("Unaged", format="%.2f"),
                "Oldest": st.column_config.TextColumn("Oldest", width="small"),
            },
        )
    else:
        st.write("No open customer balances.")
    if vendors:
        st.markdown("**Top vendor exposure**")
        if vendors_rows:
            st.dataframe(
                [
                    {
                        "Vendor": row.get("name"),
                        "Outstanding": row.get("outstanding"),
                        "AP 90+": row.get("overdue_90"),
                        "Unaged": row.get("unaged"),
                        "Oldest": _party_oldest(row),
                    }
                    for row in vendors_rows
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Vendor": st.column_config.TextColumn("Vendor", width="large"),
                    "Outstanding": st.column_config.NumberColumn("Outstanding", format="%.2f"),
                    "AP 90+": st.column_config.NumberColumn("AP 90+", format="%.2f"),
                    "Unaged": st.column_config.NumberColumn("Unaged", format="%.2f"),
                    "Oldest": st.column_config.TextColumn("Oldest", width="small"),
                },
            )
        else:
            st.write("No open vendor balances.")


def _render_benchmarks(payload: dict) -> None:
    st.markdown("##### Benchmarks")
    source = str(payload.get("benchmark_source") or "")
    if source:
        st.caption(source)
    rows = payload.get("benchmarks") or []
    if not rows:
        st.write("No benchmark rows.")
        return
    st.dataframe(
        [
            {
                "KPI": row.get("name"),
                "Actual": row.get("actual"),
                "SSDV policy": row.get("policy"),
                "Policy": row.get("policy_status"),
                "ABC baseline": row.get("peer"),
                "vs ABC": row.get("vs_peer"),
            }
            for row in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_whatif(payload: dict) -> None:
    st.markdown("##### What-if (recommend-only)")
    method = str(payload.get("whatif_method") or "")
    if method:
        st.caption(method)
    rows = list(payload.get("whatif") or [])
    if not rows:
        st.write("No what-if scenarios.")
        return
    by_prompt = {str(row.get("prompt") or ""): row for row in rows}
    prompts = list(payload.get("whatif_prompts") or [])
    chosen = None
    if prompts:
        cols = st.columns(min(2, len(prompts)))
        for i, prompt in enumerate(prompts):
            if cols[i % len(cols)].button(prompt, key=f"whatif_chip_{i}"):
                chosen = prompt
    if chosen and chosen in by_prompt:
        item = by_prompt[chosen]
        _note(str(item.get("tone") or "neutral"), str(item.get("result") or ""))
    st.dataframe(
        [
            {
                "Scenario": row.get("prompt"),
                "Result": row.get("result"),
                "Delta INR": row.get("delta_inr"),
            }
            for row in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_runway_sandbox(payload: dict) -> None:
    data = payload.get("runway") or {}
    if not data or not int(data.get("months_used") or 0):
        return
    base = base_from_dict(data)
    st.markdown("##### Runway sandbox")
    st.caption(str(data.get("method") or ""))
    if base.partial_month:
        _note("neutral", "Only a part month is posted, so the averages below are thin.")
    left, right = st.columns(2, gap="large")
    with left:
        sales_pct = st.slider("Sales change (%)", -30, 50, 0, step=5, key="rw_sales")
        opex_pct = st.slider("Operating cost change (%)", -30, 30, 0, step=5, key="rw_opex")
    with right:
        new_cost = st.number_input(
            "New monthly cost, e.g. hiring (INR)",
            min_value=0.0,
            value=0.0,
            step=10000.0,
            key="rw_cost",
        )
        ar_max = float(max(base.ar, 0))
        collected = (
            st.number_input(
                f"Receivables collected now (INR, up to {_inr_text(base.ar)})",
                min_value=0.0,
                max_value=ar_max,
                value=0.0,
                step=10000.0,
                key="rw_ar",
            )
            if ar_max > 0
            else 0.0
        )
    before, after = simulate_runway(
        base,
        Levers(
            sales_change_pct=Decimal(sales_pct),
            opex_change_pct=Decimal(opex_pct),
            new_monthly_cost=Decimal(str(new_cost)),
            ar_collected=Decimal(str(collected)),
        ),
    )
    cols = st.columns(4)
    cols[0].metric(
        "Monthly result",
        _inr_text(after.monthly_result),
        _inr_text(after.monthly_result - before.monthly_result),
    )
    cols[1].metric("Monthly burn", _inr_text(after.burn), f"was {_inr_text(before.burn)}", delta_color="off")
    cols[2].metric("Cash", _inr_text(after.cash), _inr_text(after.cash - before.cash))
    if before.runway is not None and after.runway is not None:
        runway_delta = f"{after.runway - before.runway:+} months"
    else:
        runway_delta = f"was {runway_text(before.runway)}"
    cols[3].metric("Runway", runway_text(after.runway), runway_delta, delta_color="off")


def _chart_title(title: str) -> None:
    st.markdown(f"**{title}**")


def _altair():
    import altair as alt
    import pandas as pd

    return alt, pd


def _multi_line(
    payload: dict, series: list[tuple[str, str]], title: str, *, area: bool = False
) -> None:
    try:
        alt, pd = _altair()
    except ImportError:
        frame: dict[str, list] = {}
        labels: list[str] = []
        for series_id, name in series:
            labs, values = monthly_series(payload, series_id)
            if labs:
                labels = labs
                frame[name] = values
        if not labels:
            return
        frame["month"] = labels
        _chart_title(title)
        if area:
            st.area_chart(frame, x="month", use_container_width=True)
        else:
            st.line_chart(frame, x="month", use_container_width=True)
        return

    rows: list[dict] = []
    for series_id, name in series:
        labs, values = monthly_series(payload, series_id)
        rows.extend({"month": lab, "series": name, "value": val} for lab, val in zip(labs, values))
    if not rows:
        return
    frame = pd.DataFrame(rows)
    mark = alt.Chart(frame)
    if area:
        drawn = mark.mark_area(opacity=0.55, line=True)
    else:
        drawn = mark.mark_line(strokeWidth=2.6, point=True)
    chart = (
        drawn.encode(
            x=alt.X("month:N", title=None, sort=None),
            y=alt.Y("value:Q", title="INR"),
            color=alt.Color(
                "series:N",
                legend=alt.Legend(title=None, orient="bottom"),
                scale=alt.Scale(range=["#1B4F72", "#C45C26", "#2F6F4E", "#B45309"]),
            ),
            tooltip=["month:N", "series:N", alt.Tooltip("value:Q", format=",.2f")],
        )
        .properties(height=280)
        .configure(background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(labelFontSize=12, titleFontSize=12)
    )
    _chart_title(title)
    st.altair_chart(chart, use_container_width=True)


def _bars(points: list[dict], title: str) -> None:
    _chart_title(title)
    if not points:
        st.write("No rows.")
        return
    try:
        alt, pd = _altair()
        frame = pd.DataFrame(points)
        chart = (
            alt.Chart(frame)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("label:N", title=None),
                y=alt.Y("value:Q", title="INR"),
                color=alt.Color(
                    "label:N",
                    legend=None,
                    scale=alt.Scale(range=["#1B4F72", "#C45C26", "#2F6F4E", "#B45309", "#7C6A46"]),
                ),
                tooltip=["label:N", alt.Tooltip("value:Q", format=",.2f")],
            )
            .properties(height=280)
            .configure(background="transparent")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, use_container_width=True)
    except ImportError:
        st.bar_chart({row["label"]: row["value"] for row in points}, use_container_width=True)


def _named_bars(labels: list[str], values: list[float], title: str, *, name: str = "INR") -> None:
    if not labels:
        return
    _bars([{"label": lab, "value": val} for lab, val in zip(labels, values)], title)


def _donut(points: list[dict], title: str) -> None:
    _chart_title(title)
    if not points:
        st.write("No aging rows.")
        return
    try:
        alt, pd = _altair()
        frame = pd.DataFrame(points)
        chart = (
            alt.Chart(frame)
            .mark_arc(innerRadius=68, outerRadius=120)
            .encode(
                theta=alt.Theta("value:Q"),
                color=alt.Color(
                    "label:N",
                    legend=alt.Legend(title=None, orient="bottom"),
                    scale=alt.Scale(range=["#1B4F72", "#C45C26", "#2F6F4E", "#B45309", "#7C6A46"]),
                ),
                tooltip=["label:N", alt.Tooltip("value:Q", format=",.2f")],
            )
            .properties(height=300)
            .configure(background="transparent")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, use_container_width=True)
    except ImportError:
        st.bar_chart({row["label"]: row["value"] for row in points}, use_container_width=True)


def _scorecard_chart(payload: dict) -> None:
    points = scorecard_points(payload)
    if not points:
        return
    try:
        alt, pd = _altair()
        frame = pd.DataFrame(points)
        frame["flag"] = frame["status"].map(lambda s: 1 if str(s).lower() == "breach" else 0.55)
        chart = (
            alt.Chart(frame)
            .mark_bar(cornerRadiusEnd=4, size=18)
            .encode(
                y=alt.Y("name:N", title=None, sort="-x"),
                x=alt.X("flag:Q", title=None, axis=None),
                color=alt.Color(
                    "status:N",
                    scale=alt.Scale(
                        domain=["Hold", "Breach", "n/a"],
                        range=["#2F6F4E", "#B42318", "#7C6A46"],
                    ),
                    legend=alt.Legend(title="Status", orient="bottom"),
                ),
                tooltip=["name:N", "actual:N", "status:N"],
            )
            .properties(height=max(180, 42 * len(points)))
            .configure(background="transparent")
            .configure_view(strokeWidth=0)
        )
        _chart_title("Policy scorecard")
        st.altair_chart(chart, use_container_width=True)
    except ImportError:
        _chart_title("Policy scorecard")
        st.dataframe(points, use_container_width=True, hide_index=True)


def _should_show_setup() -> bool:
    if st.session_state.get("show_setup"):
        return True
    if st.session_state.get("setup_complete"):
        return False
    return not vault_has_data()


def _render_ceo(payload: dict, db_path: str, as_of: date) -> None:
    st.markdown('<div class="om-kicker">CEO pack</div>', unsafe_allow_html=True)
    for item in payload.get("insights") or []:
        if item.get("surface") == "why":
            continue
        _note(str(item.get("tone") or "neutral"), str(item.get("text") or ""))
    _metrics(pack_tiles(payload, "ceo"))
    if _allowed("parties_intel"):
        _render_parties(payload, vendors=False)
    if _allowed("benchmarks"):
        _render_benchmarks(payload)
    if _allowed("whatif"):
        _render_whatif(payload)
        _render_runway_sandbox(payload)
    left, right = st.columns(2, gap="large")
    with left:
        _multi_line(payload, [("sales", "Taxable sales"), ("cogs", "COGS")], "Sales vs COGS")
    with right:
        _multi_line(payload, [("gross_margin", "Gross margin")], "Monthly gross margin", area=True)
    left, right = st.columns(2, gap="large")
    with left:
        _multi_line(payload, [("sales", "Sales"), ("receipts", "Receipts")], "Sales vs collections")
    with right:
        _donut(pnl_mix_points(payload), "P&L mix (COGS vs gross margin)")
    labels, profit = monthly_profit_points(payload)
    _named_bars(labels, profit, "Monthly profit (sales - COGS - operating expenses)")
    why_items = [item for item in payload.get("insights") or [] if item.get("surface") == "why"]
    if why_items:
        st.markdown("##### Why (from posted books)")
        for item in why_items:
            _note(str(item.get("tone") or "neutral"), str(item.get("text") or ""))
    st.markdown("##### Ask why")
    if not _allowed("ask_why"):
        return
    prompts = list(payload.get("why_prompts") or [])
    chosen = None
    if prompts:
        cols = st.columns(min(3, len(prompts)))
        for i, prompt in enumerate(prompts):
            if cols[i % len(cols)].button(prompt, key=f"why_chip_{i}"):
                chosen = prompt
    question = st.text_input(
        "Ask a why-question",
        placeholder="Or type a question about these books...",
        key="why_q",
    )
    ask = chosen or (question or "").strip()
    if ask:
        engine = make_engine(Path(db_path))
        with session_scope(engine) as session:
            try:
                answer = ask_books(session, ask, as_of)
            except AskError as exc:
                _note("warning", str(exc))
            else:
                _note("neutral", answer)


def _render_budget_variance(payload: dict) -> None:
    st.markdown("##### Budget vs actual — variance drivers")
    report = payload.get("budget_variance")
    if not isinstance(report, dict):
        st.caption(
            "No account budgets for this book. Add an `accounts:` section to the "
            "`.budget.yaml` file next to the vault (see the user manual, section 7.4)."
        )
        return
    st.caption(str(report.get("method") or ""))
    impact = money(str(report.get("profit_impact") or "0"))
    basis = (
        f"annual budgets pro-rated to {float(report.get('elapsed_pct') or 0):.0%} of the year"
        if report.get("basis") == "annual"
        else "budgets taken as to-date amounts"
    )
    _note(
        "success" if impact >= 0 else "warning",
        f"Budgeted ledgers are {_inr_text(abs(impact))} "
        f"{'ahead of' if impact >= 0 else 'behind'} budget on profit "
        f"({report.get('fy_code')}, {basis}).",
    )

    def _table(rows: list[dict]) -> list[dict]:
        return [
            {
                "Ledger": f"{row.get('name')} ({row.get('code')})",
                "Type": row.get("type"),
                "Actual": row.get("actual"),
                "Budget": row.get("budget"),
                "Variance": row.get("variance"),
                "Variance %": (
                    "" if row.get("variance_pct") is None else f"{float(row['variance_pct']):+.1%}"
                ),
                "Profit impact": row.get("profit_impact"),
                "": "Favourable" if row.get("favourable") else "Adverse",
            }
            for row in rows
        ]

    drivers = list(report.get("drivers") or [])
    if drivers:
        st.dataframe(_table(drivers), use_container_width=True, hide_index=True)
    else:
        st.write("Every budgeted ledger is exactly on budget.")
    rows = list(report.get("rows") or [])
    if len(rows) > len(drivers):
        with st.expander(f"All {len(rows)} budgeted ledgers"):
            st.dataframe(_table(rows), use_container_width=True, hide_index=True)
    if report.get("unmatched"):
        _note(
            "warning",
            "Budget lines with no matching ledger (check the code or name): "
            + ", ".join(str(item) for item in report["unmatched"]),
        )
    if int(report.get("unbudgeted_count") or 0):
        st.caption(
            f"{report['unbudgeted_count']} expense ledger(s) with postings have no budget "
            f"(total {_inr_text(report.get('unbudgeted_expense'))})."
        )


def _render_client_chart(payload: dict) -> None:
    client = payload.get("client_chart")
    if not isinstance(client, dict):
        return
    with st.expander("Books in the client's own chart of accounts"):
        st.caption(
            "The same posted books, shown with this client's own ledger codes, names and "
            "groups. The standard ledger is what OfficeMitra uses for KPIs. Download Excel "
            "for the full trial balance and P&L in the client's chart."
        )
        view = st.radio(
            "Show",
            ["Profit & loss (year to date)", "Trial balance"],
            horizontal=True,
            key="client_chart_view",
        )
        if view == "Trial balance":
            st.dataframe(
                [
                    {
                        "Code": row.get("client_code") or "",
                        "Ledger": row.get("client_name"),
                        "Group": row.get("client_group") or "",
                        "Debit": row.get("debit"),
                        "Credit": row.get("credit"),
                        "Balance (Dr +)": row.get("balance"),
                        "Standard": f"{row.get('standard_code')} {row.get('standard_name')}",
                    }
                    for row in client.get("trial_balance") or []
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                f"Totals: debit {_inr_text(client.get('tb_total_debit'))} · "
                f"credit {_inr_text(client.get('tb_total_credit'))}"
            )
            return
        rows = []
        for block in client.get("pnl") or []:
            for item in block.get("ledgers") or []:
                rows.append(
                    {
                        "Type": str(block.get("type") or "").title(),
                        "Group": block.get("group"),
                        "Code": item.get("client_code") or "",
                        "Ledger": item.get("client_name"),
                        "Amount": item.get("amount"),
                    }
                )
            rows.append(
                {
                    "Type": "",
                    "Group": f"Total {block.get('group')}",
                    "Code": "",
                    "Ledger": "",
                    "Amount": block.get("total"),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_cfo(payload: dict) -> None:
    st.markdown('<div class="om-kicker">CFO pack</div>', unsafe_allow_html=True)
    _metrics(pack_tiles(payload, "cfo"))
    if _allowed("budget_variance"):
        _render_budget_variance(payload)
    _render_client_chart(payload)
    st.markdown("##### Cash forecast (open AR/AP, no sales plan)")
    fc = payload.get("cash_forecast") or {}
    if fc.get("method"):
        st.caption(str(fc["method"]))
    _bars(cash_forecast_points(payload), "Cash today vs 30 / 60 / 90 days")
    horizons = list(fc.get("horizons") or [])
    if horizons:
        st.dataframe(
            [
                {
                    "Horizon": row.get("label"),
                    "AR in": row.get("ar_in"),
                    "AP out": row.get("ap_out"),
                    "GST out": row.get("gst_out"),
                    "Salary out": row.get("salary_out"),
                    "Net": row.get("net"),
                    "Cash": row.get("cash"),
                }
                for row in horizons
            ],
            use_container_width=True,
            hide_index=True,
        )
    if fc.get("blocked_ar") not in (None, "", "0.00"):
        _note(
            "warning",
            f"Unscheduled AR {_inr_text(fc.get('blocked_ar'))} is not in the 30/60/90 timing.",
        )
    left, right = st.columns(2, gap="large")
    with left:
        _donut(aging_points(payload, "ar_aging"), "AR aging")
    with right:
        _donut(aging_points(payload, "ap_aging"), "AP aging")
    left, right = st.columns(2, gap="large")
    with left:
        _bars(aging_points(payload, "ar_aging"), "AR aging (bars)")
    with right:
        _bars(aging_points(payload, "ap_aging"), "AP aging (bars)")
    if _allowed("parties_intel"):
        _render_parties(payload)
    left, right = st.columns(2, gap="large")
    with left:
        _multi_line(
            payload,
            [("receipts", "Receipts"), ("payments", "Vendor payments")],
            "Cash in vs cash out",
            area=True,
        )
    with right:
        _bars(gst_points(payload), "GST position")
    left, right = st.columns(2, gap="large")
    with left:
        _bars(
            kpi_points(
                payload,
                [
                    ("dso", "DSO days"),
                    ("dio", "DIO days"),
                    ("dpo", "DPO days"),
                    ("ccc", "Cash conversion cycle"),
                ],
            ),
            "Cash cycle (days)",
        )
    with right:
        banks = list(payload.get("banks") or [])
        if banks:
            _named_bars(
                [str(b.get("label")) for b in banks],
                [float(b.get("balance") or 0) for b in banks],
                "Cash and bank position",
            )
        else:
            st.caption("No bank or cash ledgers posted yet.")
    for item in payload.get("insights") or []:
        if item.get("surface") in {"aging", "cfo"}:
            _note(str(item.get("tone") or "neutral"), str(item.get("text") or ""))


def _render_board(payload: dict) -> None:
    st.markdown('<div class="om-kicker">Board pack</div>', unsafe_allow_html=True)
    flags = payload.get("red_flags") or []
    if flags:
        st.markdown("##### Red flags")
        for item in flags:
            _note(str(item.get("tone") or "danger"), str(item.get("text") or ""))
    else:
        _note("success", "No Board red flags on DSO policy, cash, equity, or last-month profit.")
    _metrics(pack_tiles(payload, "board"))
    left, right = st.columns(2, gap="large")
    with left:
        _bars(
            kpi_points(
                payload,
                [("assets", "Assets"), ("liabilities", "Liabilities"), ("equity", "Equity")],
            ),
            "Balance sheet",
        )
    with right:
        _bars(
            kpi_points(
                payload,
                [("ar", "Receivables"), ("inventory", "Inventory"), ("ap", "Payables")],
            ),
            "Working capital parts",
        )
    left, right = st.columns(2, gap="large")
    with left:
        _scorecard_chart(payload)
    with right:
        _bars(
            kpi_points(
                payload,
                [
                    ("dso", "DSO"),
                    ("dio", "DIO"),
                    ("dpo", "DPO"),
                    ("ccc", "Cash conversion cycle"),
                ],
            ),
            "Cash conversion (days)",
        )
    rows = payload.get("scorecard") or []
    if rows:
        st.write("")
        st.dataframe(rows, use_container_width=True, hide_index=True)
    if _allowed("benchmarks", note=False):
        _render_benchmarks(payload)
    if _allowed("parties_intel", note=False):
        _render_parties(payload, limit=5)


def _render_charts(payload: dict) -> None:
    st.markdown('<div class="om-kicker">Chart pack</div>', unsafe_allow_html=True)
    left, right = st.columns(2, gap="large")
    with left:
        _multi_line(
            payload,
            [("sales", "Sales"), ("purchases", "Purchases"), ("opex", "Operating expenses")],
            "Activity",
        )
    with right:
        _multi_line(payload, [("sales", "Sales"), ("cogs", "COGS")], "Sales vs COGS")
    left, right = st.columns(2, gap="large")
    with left:
        _multi_line(
            payload,
            [("receipts", "Receipts"), ("payments", "Vendor payments")],
            "Cash movement",
            area=True,
        )
    with right:
        _multi_line(payload, [("gross_margin", "Gross margin")], "Monthly gross margin", area=True)
    left, right = st.columns(2, gap="large")
    with left:
        _donut(pnl_mix_points(payload), "P&L mix (COGS vs gross margin)")
    with right:
        labels, profit = monthly_profit_points(payload)
        _named_bars(labels, profit, "Monthly profit")
    left, right = st.columns(2, gap="large")
    with left:
        _bars(aging_points(payload, "ar_aging"), "AR aging")
    with right:
        _bars(aging_points(payload, "ap_aging"), "AP aging")


_RISK_LABEL = {"red": "🔴 Critical", "amber": "🟠 Watch", "green": "🟢 Healthy"}


def _render_firm(rows: list[dict], *, hidden: int, limit: int | None, as_of: date) -> None:
    st.markdown('<div class="om-kicker">Practice</div>', unsafe_allow_html=True)
    st.subheader("Client books")
    st.caption(
        "Each row is one client vault (separate SQLite books), as of the date in the sidebar. "
        "This table is a practice roster — not a consolidated group P&L. "
        "CEO / CFO / Board / Chart packs only open after you open a client book below "
        "(or pick that pack in the sidebar with the matching Vault selected)."
    )
    if hidden:
        cap = limit if limit is not None else "the plan"
        _note(
            "warning",
            f"{hidden} further vault(s) are hidden by the company limit ({cap}).",
        )
    if not rows:
        st.write("No posted client books yet. Use **Change data source** to import one.")
        return
    for row in rows:
        if row.get("error"):
            _note("danger", f"{row['company']}: {row['error']}")
    counts = {band: sum(1 for row in rows if row.get("risk") == band) for band in _RISK_LABEL}
    st.markdown(
        " · ".join(f"**{counts[band]}** {label}" for band, label in _RISK_LABEL.items())
    )
    st.caption(
        "Sorted by risk, then shortest cash runway. Risk combines the board red flags "
        "with runway (red below 3 months, amber below 6)."
    )
    st.dataframe(
        [
            {
                "Risk": _RISK_LABEL.get(str(row.get("risk") or ""), ""),
                "Client": row["company"],
                "Runway": row.get("runway") or "",
                "Top alert": row.get("top_alert") or "",
                "Revenue": row["sales"],
                "AR 90+": row["ar_90"],
                "Cash": row["cash"],
                "Working capital": row["working_capital"],
                "Score": row.get("score") or "",
                "Reviewed": row.get("reviewed") or "no",
                "Vault": row["vault"],
            }
            for row in rows
        ],
        use_container_width=True,
        hide_index=True,
    )
    labels = [f"{row['company']} ({row['vault']})" for row in rows]
    by_label = dict(zip(labels, rows, strict=True))
    chosen = st.selectbox("Open a client book", labels, key="firm_open_choice")
    pack = st.selectbox(
        "Open into pack",
        ["CEO", "CFO", "Board", "Charts"],
        format_func=lambda s: {
            "CEO": "CEO pack",
            "CFO": "CFO pack",
            "Board": "Board pack",
            "Charts": "Chart pack",
        }[s],
        key="firm_open_pack",
    )
    if st.button("Open selected book", type="primary", key="firm_open_btn"):
        target = by_label[chosen]
        st.session_state.pending_vault = target["db_path"]
        st.session_state.pending_screen = pack
        st.rerun()
    st.caption(f"As of {as_of.isoformat()}. Same facts as `ssdv firm`.")


def _signoff_label(payload: dict) -> str:
    approval = payload.get("approval") if isinstance(payload.get("approval"), dict) else {}
    if approval.get("approved"):
        return f"Approved by {html.escape(str(approval.get('approved_by') or 'partner'))}"
    if payload.get("reviewed"):
        return "Reviewed — awaiting partner approval" if approval.get("required") else "Reviewed"
    return "Not reviewed"


def _render_thresholds(payload: dict, db_path: str) -> None:
    info = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
    rows = list(info.get("fields") or [])
    if not rows:
        return
    title = "Alert thresholds (custom for this client)" if info.get("custom") else "Alert thresholds (defaults)"
    with st.expander(title):
        st.caption(
            "Limits used for this client's alerts, scorecard, benchmarks, what-if and risk "
            "band. Change them to suit the business — for example a longer DSO limit for a "
            "distributor that gives 90-day credit. Saved only for this client book."
        )
        values: dict[str, float] = {}
        cols = st.columns(3)
        for i, row in enumerate(rows):
            label = f"{row['label']} ({row['unit']})" + (" *" if row.get("custom") else "")
            values[row["name"]] = cols[i % 3].number_input(
                label,
                value=float(row["value"]),
                step=1.0 if row["unit"] in {"days", "months"} else 0.5,
                key=f"threshold_{row['name']}",
            )
        st.caption("* differs from the default.")
        col1, col2 = st.columns(2)
        if col1.button("Save thresholds for this client", type="primary", key="threshold_save"):
            try:
                save_policy(Path(db_path), build_policy(values, percent=True))
            except PolicyError as exc:
                st.error(str(exc))
                return
            st.cache_data.clear()
            st.rerun()
        if info.get("custom") and col2.button("Reset to defaults", key="threshold_reset"):
            thresholds_path(Path(db_path)).unlink(missing_ok=True)
            st.cache_data.clear()
            st.rerun()


def _render_partner_approval(payload: dict, db_path: str, as_of: date) -> None:
    approval = payload.get("approval") if isinstance(payload.get("approval"), dict) else {}
    required = bool(approval.get("required"))
    title = "Partner approval" if required else "Partner approval (off)"
    with st.expander(title, expanded=required and bool(payload.get("reviewed"))):
        st.caption(
            "A second sign-off before the Board PPT: the preparer marks the books reviewed, "
            "then the partner approves with a PIN. This is a sign-off record on this PC, "
            "not a login — keep the PIN with the partner."
        )
        if not required:
            name = st.text_input("Partner name", key="approval_setup_name")
            pin = st.text_input("Choose a partner PIN", type="password", key="approval_setup_pin")
            again = st.text_input("Repeat the PIN", type="password", key="approval_setup_pin2")
            if st.button("Turn on partner approval", key="approval_setup_btn"):
                if pin != again:
                    st.error("The two PINs do not match.")
                    return
                try:
                    set_partner_pin(name, pin)
                except ApprovalError as exc:
                    st.error(str(exc))
                    return
                st.cache_data.clear()
                st.rerun()
            return

        if approval.get("approved"):
            _note(
                "success",
                f"Approved by {html.escape(str(approval.get('approved_by')))} "
                f"on {str(approval.get('approved_at') or '')[:10]} for this as-of date.",
            )
        elif payload.get("reviewed"):
            _note("warning", "Reviewed. Waiting for the partner to approve.")
        else:
            _note("neutral", "Mark the books reviewed first; then the partner can approve.")
        pin = st.text_input("Partner PIN", type="password", key="approval_pin")
        col1, _, col3 = st.columns(3)
        try:
            if not approval.get("approved") and col1.button(
                "Approve as partner",
                type="primary",
                disabled=not payload.get("reviewed"),
                key="approval_approve",
            ):
                approve(
                    Path(db_path),
                    as_of,
                    voucher_count=voucher_count(Path(db_path)),
                    reviewed=bool(payload.get("reviewed")),
                    pin=pin,
                )
                st.cache_data.clear()
                st.rerun()
            if approval.get("approved") and col1.button(
                "Withdraw approval", key="approval_withdraw"
            ):
                withdraw_approval(Path(db_path), pin=pin)
                st.cache_data.clear()
                st.rerun()
            if col3.button("Turn off partner approval", key="approval_disable"):
                disable_partner_approval(pin)
                st.cache_data.clear()
                st.rerun()
        except ApprovalError as exc:
            st.error(str(exc))


def _render_report(payload: dict, db_path: str, as_of: date, screen: str) -> None:
    st.markdown('<div class="om-kicker">Posted books</div>', unsafe_allow_html=True)
    st.subheader(str(payload.get("company") or ""))
    wc = _inr_text((payload.get("kpis") or {}).get("working_capital"))
    score = payload.get("data_quality_score")
    band = payload.get("data_quality_band") or ""
    st.markdown(
        f'<div class="om-meta">'
        f"<span>Scenario {payload.get('scenario')}</span>"
        f"<span>As of {payload.get('as_of')}</span>"
        f"<span>Working capital {wc}</span>"
        f"<span>Quality {score} {band}</span>"
        f"<span>{_signoff_label(payload)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    g2b = (payload.get("data_quality_breakdown") or {}).get("gstr2b")
    if isinstance(g2b, dict):
        if g2b.get("checked"):
            st.caption(
                f"GSTR-2B ITC gap {g2b.get('itc_gap')} · "
                f"{g2b.get('mismatch_count')} flag(s) · "
                f"quality −{g2b.get('deduction')} pts"
            )
        elif g2b.get("reason"):
            st.caption(f"GSTR-2B: {g2b.get('reason')}")
    if payload.get("ppt_block_reason") and not payload.get("ppt_allowed"):
        _note("warning", str(payload["ppt_block_reason"]))
    bva = payload.get("budget_vs_actual") if isinstance(payload.get("budget_vs_actual"), dict) else {}
    if bva.get("sales_budget"):
        st.caption(
            f"Sales vs budget: actual {bva.get('sales_actual')}  "
            f"budget {bva.get('sales_budget')}  variance {bva.get('variance_abs')} "
            f"({bva.get('source')})"
        )
    elif bva.get("source") == "missing":
        st.caption(
            "No budget sidecar for this imported vault. "
            f"Add `{Path(db_path).stem}.budget.yaml` next to the SQLite file (sales: amount)."
        )
    prepared_by = st.text_input(
        "Prepared by (optional, shown on the Board PPT)",
        value=str(st.session_state.get("prepared_by") or ""),
        key="prepared_by_input",
    )
    if st.button("Mark books reviewed for this as-of", key="mark_reviewed"):
        st.session_state["prepared_by"] = prepared_by
        engine = make_engine(Path(db_path))
        create_schema(engine)
        with session_scope(engine) as session:
            mark_reviewed(Path(db_path), as_of, session=session, reviewed_by=prepared_by)
        st.cache_data.clear()
        st.rerun()
    if _allowed("partner_approval", note=False):
        _render_partner_approval(payload, db_path, as_of)
    if _allowed("alert_thresholds", note=False):
        _render_thresholds(payload, db_path)
    st.download_button(
        "Download full report (HTML)",
        data=render_dashboard(payload).encode("utf-8"),
        file_name=f"officemitra-{payload.get('as_of')}.html",
        mime="text/html",
        help="Open this file in Edge, then Ctrl+P and Save as PDF if you want a full-page print.",
    )
    if _allowed("board_pack", note=False):
        st.download_button(
            "Download Board pack (PDF)",
            data=render_board_pdf(payload),
            file_name=f"officemitra-board-{payload.get('as_of')}.pdf",
            mime="application/pdf",
            help="Automated Board pack from posted journals. Recommend-only.",
        )
    exports_ok = _allowed("export_excel_ppt")
    if exports_ok:
        st.download_button(
            "Download Excel",
            data=_excel_bytes(payload),
            file_name=f"officemitra-{payload.get('as_of')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ppt_plan_ok = exports_ok and _ent().allows("board_pack")
    if ppt_plan_ok and payload.get("ppt_allowed"):
        st.download_button(
            "Download Board PPT",
            data=_ppt_bytes(payload),
            file_name=f"officemitra-board-{payload.get('as_of')}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    elif ppt_plan_ok:
        st.caption(
            "Board PPT stays blocked until quality is at least 70, books are reviewed"
            + (
                ", and the partner has approved."
                if (payload.get("approval") or {}).get("required")
                else "."
            )
        )
    screen_feature = {"CFO": "cfo_pack", "Board": "board_pack", "Charts": "chart_pack"}.get(screen)
    if screen_feature and not _ent().allows(screen_feature):
        _note("warning", upgrade_note(screen_feature, _ent()))
        return
    if screen == "CEO":
        _render_ceo(payload, db_path, as_of)
    elif screen == "CFO":
        _render_cfo(payload)
    elif screen == "Board":
        _render_board(payload)
    else:
        _render_charts(payload)


def main() -> None:
    global _ENT
    _ENT = current_entitlements()
    cli = _cli()
    st.markdown(_CSS, unsafe_allow_html=True)
    if "as_of" not in st.session_state:
        st.session_state.as_of = date.fromisoformat(cli.as_of)
    if "pending_as_of" in st.session_state:
        st.session_state.as_of = st.session_state.pop("pending_as_of")
    if "pending_vault" in st.session_state:
        st.session_state.vault = st.session_state.pop("pending_vault")
    if "pending_screen" in st.session_state:
        st.session_state.screen = st.session_state.pop("pending_screen")
    data_dir = user_data_dir() / "data"
    found = sorted(str(path) for path in data_dir.glob("*.sqlite")) if data_dir.exists() else []
    posted = discover_vaults(data_dir if data_dir.exists() else None)
    visible, hidden = apply_company_limit(posted)
    show_firm = len(visible) > 1 or hidden > 0
    screens = (
        ["Firm", "CEO", "CFO", "Board", "Charts", "Connect"]
        if show_firm
        else ["CEO", "CFO", "Board", "Charts", "Connect"]
    )
    if "screen" not in st.session_state:
        st.session_state.screen = "Firm" if show_firm else "CEO"
    elif st.session_state.screen not in screens:
        st.session_state.screen = screens[0]

    # Sync roster pick → Vault *before* the selectbox widget is created.
    screen_now = str(st.session_state.get("screen") or "CEO")
    if show_firm and screen_now in {"CEO", "CFO", "Board", "Charts"}:
        choice = st.session_state.get("firm_open_choice")
        if isinstance(choice, str) and "(" in choice and choice.endswith(")"):
            vault_stem = choice.rsplit("(", 1)[-1][:-1].strip()
            match = next((str(path) for path in visible if path.stem == vault_stem), None)
            if match:
                st.session_state.vault = match

    with st.sidebar:
        st.markdown('<div class="om-kicker">OfficeMitra</div>', unsafe_allow_html=True)
        st.header("Books")
        options = found or [cli.db]
        preferred = st.session_state.get("vault") or cli.db
        if preferred not in options:
            options = [preferred, *options]
        default_index = options.index(preferred) if preferred in options else 0
        db_path = st.selectbox("Vault", options, index=default_index, key="vault")
        as_of = st.date_input("As of", key="as_of")
        if st.button("Use ABC year-end 31 Mar 2026"):
            st.session_state.pending_as_of = date(2026, 3, 31)
            st.rerun()
        st.radio(
            "Screen",
            screens,
            format_func=lambda s: {
                "Firm": "All client books",
                "CEO": "CEO pack",
                "CFO": "CFO pack",
                "Board": "Board pack",
                "Charts": "Chart pack",
                "Connect": "Change data source",
            }.get(s, s),
            key="screen",
        )
        if show_firm and st.button("All client books"):
            st.session_state.pending_screen = "Firm"
            st.rerun()
        if st.button("Change data source"):
            st.session_state["show_setup"] = True
            st.session_state.pop("setup_complete", None)
            st.rerun()
        ent = _ent()
        st.caption(ent.status_line())
        if ent.problem:
            st.warning(f"Licence not accepted: {ent.problem}")
        st.write("Unbalanced books never get a chart. Same facts as `ssdv mis --json`.")
        with st.expander("Full-page screenshot"):
            st.write(
                "Edge cannot see below the fold on this app until you download the HTML report "
                "or use: F12 → Ctrl+Shift+P → Capture full size screenshot after a refresh. "
                "Best: Download Board pack (PDF), or Download full report (HTML) then Ctrl+P in Edge."
            )

    _unlock_full_page()
    render_brand_header()

    screen = str(st.session_state.get("screen") or "CEO")

    if _should_show_setup() or screen == "Connect":
        if screen == "Connect":
            st.session_state["show_setup"] = True
        render_setup_wizard()
        return

    st.caption(
        "Read-only KPIs and AI notes from posted journals. "
        "Not a live login to Tally, Zoho, Busy, or MitraBooks."
    )

    if screen == "Firm":
        rows = [
            _firm_row(str(path), as_of.isoformat(), _sidecar_stamp(str(path))) for path in visible
        ]
        _render_firm(rows, hidden=hidden, limit=effective_company_limit(), as_of=as_of)
        return

    if show_firm and st.button("← All client books", key="back_to_firm"):
        st.session_state.pending_screen = "Firm"
        st.rerun()

    if not Path(db_path).exists():
        st.error("No books loaded yet. Use **Change data source** in the sidebar to import.")
        return
    payload = _payload(db_path, as_of.isoformat(), _sidecar_stamp(db_path))
    if as_of > date(2026, 3, 31):
        st.warning(
            "As of is after ABC year-end (31 Mar 2026), so this FY has no sales. "
            "Click **Use ABC year-end 31 Mar 2026** in the sidebar."
        )
    _render_report(payload, db_path, as_of, screen)


if __name__ == "__main__":
    main()
