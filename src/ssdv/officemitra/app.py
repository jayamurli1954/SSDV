from __future__ import annotations

import argparse
import html
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from ssdv.ask import AskError, ask_books
from ssdv.connectors import ConnectorError, ConnectorNotReady, list_connectors, load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.ingest import IngestError
from ssdv.mis import mis_snapshot, snapshot_payload
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
from ssdv.officemitra.boardpack import render_board_pdf
from ssdv.officemitra.dashboard import render_dashboard
from ssdv.paths import connect_db_path, default_db_path, repo_root

st.set_page_config(page_title="OfficeMitra", layout="wide", initial_sidebar_state="expanded")

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
def _payload(db_path: str, as_of: str) -> dict:
    engine = make_engine(Path(db_path))
    create_schema(engine)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, date.fromisoformat(as_of))
        peer = None
        if snap.scenario_id != "baseline":
            from ssdv.mis.benchmarks import load_baseline_peer

            peer = load_baseline_peer(snap.as_of, exclude=Path(db_path))
        return snapshot_payload(snap, "all", peer=peer)


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


def _chart_title(title: str) -> None:
    st.markdown(f"**{title}**")


def _altair():
    import altair as alt
    import pandas as pd

    return alt, pd


def _multi_line(payload: dict, series: list[tuple[str, str]], title: str, *, area: bool = False) -> None:
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


def _write_upload(upload, suffix: str) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="ssdv_connect_"))
    path = folder / f"export{suffix}"
    path.write_bytes(upload.getvalue())
    return path


def _render_connect() -> None:
    st.markdown('<div class="om-kicker">Read-only extract</div>', unsafe_allow_html=True)
    st.subheader("Connect another application")
    st.write(
        "SSDV never writes back to Tally, Zoho, Busy, or MitraBooks. "
        "Export a journal / day book to CSV, map ledgers to SSDV account codes, "
        "then KPI packs and AI notes run on posted books."
    )
    rows = [
        {
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "how": item.hint,
        }
        for item in list_connectors()
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    journals = st.file_uploader(
        "Journal CSV",
        type=["csv"],
        help="voucher_id, date, voucher_type, account, debit, credit",
    )
    mapping = st.file_uploader("Ledger map (optional)", type=["csv", "yml", "yaml"])
    name = st.text_input("Company name", value="")
    replace = st.checkbox("Replace books already in the connect vault", value=False)
    if st.button("Extract and post into SSDV", type="primary"):
        if journals is None:
            st.error("Upload a journal CSV first. Sample shape: examples/generic_ingest/journals.csv")
            return
        journal_path = _write_upload(journals, ".csv")
        map_path = None
        if mapping is not None:
            suffix = Path(str(mapping.name)).suffix.lower() or ".csv"
            map_path = _write_upload(mapping, suffix)
        db_path = connect_db_path()
        try:
            result = load_into_vault(
                db_path,
                source="generic",
                journals=journal_path,
                account_map=map_path,
                company_name=name or None,
                force=replace,
            )
        except ConnectorNotReady as exc:
            st.error(str(exc))
            return
        except ConnectorError as exc:
            st.error(str(exc))
            return
        except IngestError as exc:
            st.error(str(exc))
            return
        st.session_state["pending_vault"] = str(db_path)
        st.session_state["pending_screen"] = "CEO"
        st.cache_data.clear()
        st.rerun()


def _render_ceo(payload: dict, db_path: str, as_of: date) -> None:
    st.markdown('<div class="om-kicker">OfficeMitra notes</div>', unsafe_allow_html=True)
    for item in payload.get("insights") or []:
        if item.get("surface") == "why":
            continue
        _note(str(item.get("tone") or "neutral"), str(item.get("text") or ""))
    st.markdown("##### CEO pack")
    _metrics(pack_tiles(payload, "ceo"))
    _render_benchmarks(payload)
    _render_whatif(payload)
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
    prompts = list(payload.get("why_prompts") or [])
    st.markdown("##### Ask why")
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


def _render_cfo(payload: dict) -> None:
    st.markdown('<div class="om-kicker">Cash and aging</div>', unsafe_allow_html=True)
    _metrics(pack_tiles(payload, "cfo"))
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
        _note("warning", f"Unscheduled AR {_inr_text(fc.get('blocked_ar'))} is not in the 30/60/90 timing.")
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
        _bars(
            kpi_points(
                payload,
                [("hdfc", "HDFC"), ("icici", "ICICI"), ("od", "OD")],
            ),
            "Bank position",
        )
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
    _render_benchmarks(payload)


def _render_charts(payload: dict) -> None:
    st.markdown('<div class="om-kicker">From posted journals</div>', unsafe_allow_html=True)
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


def _render_report(payload: dict, db_path: str, as_of: date, screen: str) -> None:
    st.markdown('<div class="om-kicker">Posted books</div>', unsafe_allow_html=True)
    st.subheader(str(payload.get("company") or ""))
    wc = _inr_text((payload.get("kpis") or {}).get("working_capital"))
    st.markdown(
        f'<div class="om-meta">'
        f"<span>Scenario {payload.get('scenario')}</span>"
        f"<span>As of {payload.get('as_of')}</span>"
        f"<span>Working capital {wc}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download full report (HTML)",
        data=render_dashboard(payload).encode("utf-8"),
        file_name=f"officemitra-{payload.get('as_of')}.html",
        mime="text/html",
        help="Open this file in Edge, then Ctrl+P and Save as PDF if you want a full-page print.",
    )
    st.download_button(
        "Download Board pack (PDF)",
        data=render_board_pdf(payload),
        file_name=f"officemitra-board-{payload.get('as_of')}.pdf",
        mime="application/pdf",
        help="Automated Board pack from posted journals. Recommend-only. PPT is not in this pack.",
    )
    if screen == "CEO":
        _render_ceo(payload, db_path, as_of)
    elif screen == "CFO":
        _render_cfo(payload)
    elif screen == "Board":
        _render_board(payload)
    else:
        _render_charts(payload)


def main() -> None:
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
    data_dir = repo_root() / "data"
    found = sorted(str(path) for path in data_dir.glob("*.sqlite")) if data_dir.exists() else []

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
        st.radio("Screen", ["CEO", "CFO", "Board", "Charts", "Connect"], key="screen")
        st.write("Unbalanced books never get a chart. Same facts as `ssdv mis --json`.")
        with st.expander("Full-page screenshot"):
            st.write(
                "Edge cannot see below the fold on this app until you download the HTML report "
                "or use: F12 → Ctrl+Shift+P → Capture full size screenshot after a refresh. "
                "Best: Download Board pack (PDF), or Download full report (HTML) then Ctrl+P in Edge."
            )

    _unlock_full_page()

    screen = str(st.session_state.get("screen") or "CEO")
    st.title("OfficeMitra")
    st.write(
        "Read-only KPIs and AI notes from posted journals. "
        "Not a live login to Tally, Zoho, Busy, or MitraBooks."
    )

    if screen == "Connect":
        _render_connect()
        return
    if not Path(db_path).exists():
        st.error("No SQLite vault at that path. Open Connect, or run ssdv init / ssdv connect.")
        return
    payload = _payload(db_path, as_of.isoformat())
    if as_of > date(2026, 3, 31):
        st.warning(
            "As of is after ABC year-end (31 Mar 2026), so this FY has no sales. "
            "Click **Use ABC year-end 31 Mar 2026** in the sidebar."
        )
    _render_report(payload, db_path, as_of, screen)


if __name__ == "__main__":
    main()
