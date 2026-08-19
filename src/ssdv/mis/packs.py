from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ssdv.mis.kpis import MisSnapshot
from ssdv.mis.policy import (
    AR_TO_SALES_STRESS,
    COGS_RATIO_MAX,
    COLLECTION_EFFICIENCY_MIN,
    CUSTOMER_SHARE_MAX,
    DSO_DAYS_MAX,
    INVENTORY_TO_SALES_MAX,
    VENDOR_SHARE_MAX,
)
from ssdv.money import ZERO, money

Tone = str  # success | warning | danger | neutral


@dataclass(frozen=True)
class Tile:
    id: str
    label: str
    value: str
    tone: Tone
    drill: str


@dataclass(frozen=True)
class ScorecardRow:
    id: str
    name: str
    policy: str
    actual: str
    status: str
    tone: Tone


@dataclass(frozen=True)
class MisPack:
    id: str
    title: str
    tiles: tuple[Tile, ...]
    scorecard: tuple[ScorecardRow, ...]
    notes: tuple[str, ...]


def _inr(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _pct(ratio: Decimal, digits: int = 0) -> str:
    return f"{(ratio * 100):.{digits}f}%"


def _days(value: int | None) -> str:
    return "n/a" if value is None else f"{value} d"


def _times(ratio: Decimal) -> str:
    return f"{ratio:.2f}x"


def _tone_high(value: Decimal, limit: Decimal, *, invert: bool = False) -> Tone:
    breach = value >= limit
    if invert:
        breach = value < limit
    return "danger" if breach else "success"


def _growth(snap: MisSnapshot) -> str:
    if snap.sales_growth is None:
        return "n/a"
    sign = "+" if snap.sales_growth >= ZERO else ""
    return f"{sign}{_pct(snap.sales_growth, 1)}"


def scorecard(snap: MisSnapshot) -> tuple[ScorecardRow, ...]:
    m = snap.metrics
    dso_status = "Hold"
    dso_tone: Tone = "success"
    if snap.dso is None:
        dso_status, dso_tone = "n/a", "neutral"
    elif snap.dso > DSO_DAYS_MAX:
        dso_status, dso_tone = "Breach", "danger"

    equity_ok = snap.equity >= ZERO
    rows = (
        ScorecardRow(
            "customer_concentration",
            "Customer concentration",
            "Top customer < 35%",
            _pct(m.top_customer_share),
            "Breach" if m.top_customer_share >= CUSTOMER_SHARE_MAX else "Hold",
            _tone_high(m.top_customer_share, CUSTOMER_SHARE_MAX),
        ),
        ScorecardRow(
            "vendor_dependency",
            "Vendor dependency",
            "Top vendor < 55%",
            _pct(m.top_vendor_share),
            "Breach" if m.top_vendor_share >= VENDOR_SHARE_MAX else "Hold",
            _tone_high(m.top_vendor_share, VENDOR_SHARE_MAX),
        ),
        ScorecardRow(
            "collections",
            "Collections",
            "DSO <= 120 days",
            _days(snap.dso),
            dso_status,
            dso_tone,
        ),
        ScorecardRow(
            "stock",
            "Stock",
            "Inventory / sales < 0.45",
            f"{m.inventory_to_sales:.2f}",
            "Breach" if m.inventory_to_sales >= INVENTORY_TO_SALES_MAX else "Hold",
            _tone_high(m.inventory_to_sales, INVENTORY_TO_SALES_MAX),
        ),
        ScorecardRow(
            "gross_margin",
            "Gross margin",
            "COGS / sales < 0.84",
            f"{m.cogs_ratio:.2f}",
            "Breach" if m.cogs_ratio >= COGS_RATIO_MAX else "Hold",
            _tone_high(m.cogs_ratio, COGS_RATIO_MAX),
        ),
        ScorecardRow(
            "solvency",
            "Solvency",
            "Equity >= 0 after close",
            _inr(snap.equity),
            "Hold" if equity_ok else "Negative",
            "success" if equity_ok else "danger",
        ),
        ScorecardRow(
            "cash_stress",
            "Cash conversion",
            "Watch CCC and OD floor",
            _days(snap.ccc),
            "OD drawn" if snap.od < ZERO else "Hold",
            "warning" if snap.od < ZERO else "success",
        ),
    )
    return rows


def ceo_pack(snap: MisSnapshot) -> MisPack:
    vs_plan = "n/a"
    if snap.fy.plan > ZERO:
        vs_plan = _pct(_share_safe(snap.fy.sales, snap.fy.plan), 1)
    gm_tone: Tone = "success"
    if snap.fy.gm_pct < money("0.10"):
        gm_tone = "danger"
    elif snap.fy.gm_pct < money("0.18"):
        gm_tone = "warning"
    coll = snap.collection_efficiency
    coll_tone: Tone = "neutral"
    if snap.fy.sales > ZERO:
        coll_tone = "danger" if coll < COLLECTION_EFFICIENCY_MIN else "success"
    wc_tone: Tone = "danger" if snap.working_capital < ZERO else "neutral"
    profit_tone: Tone = "danger" if snap.monthly_profit < ZERO else "neutral"
    last_month = snap.series.labels[-1] if snap.series.labels else "Last month"
    tiles = (
        Tile("sales", f"{snap.fy.fy_code} taxable sales", _inr(snap.fy.sales), "neutral", "410000"),
        Tile("gm", "Gross profit %", _pct(snap.fy.gm_pct, 1), gm_tone, "cogs"),
        Tile(
            "cash",
            "Cash position",
            _inr(snap.cash),
            "danger" if snap.cash < ZERO else "success",
            "111000",
        ),
        Tile("ar", "Receivables outstanding", _inr(snap.ar), "neutral", "120000"),
        Tile("ap", "Payables outstanding", _inr(snap.ap), "neutral", "210000"),
        Tile("inv", "Inventory value", _inr(snap.inventory), "neutral", "130000"),
        Tile(
            "working_capital",
            "Operating working capital",
            _inr(snap.working_capital),
            wc_tone,
            "wc",
        ),
        Tile(
            "monthly_profit",
            f"{last_month} profit",
            _inr(snap.monthly_profit),
            profit_tone,
            "pnl",
        ),
        Tile(
            "collection_efficiency",
            "Collection efficiency",
            _pct(coll, 1),
            coll_tone,
            "receipts",
        ),
        Tile("growth", "Sales growth %", _growth(snap), "neutral", "sales"),
        Tile(
            "ccc",
            "Cash conversion cycle",
            _days(snap.ccc),
            "danger" if (snap.dso is not None and snap.dso > DSO_DAYS_MAX) else "warning",
            "ccc",
        ),
        Tile(
            "current_ratio",
            "Current ratio",
            _times(snap.current_ratio),
            "danger"
            if snap.current_liabilities > ZERO and snap.current_ratio < money("1")
            else "success"
            if snap.current_liabilities > ZERO
            else "neutral",
            "ca_cl",
        ),
        Tile(
            "quick_ratio",
            "Quick ratio",
            _times(snap.quick_ratio),
            "danger"
            if snap.current_liabilities > ZERO and snap.quick_ratio < money("1")
            else "success"
            if snap.current_liabilities > ZERO
            else "neutral",
            "quick",
        ),
        Tile(
            "monthly_net_cash",
            "Last-month net cash",
            _inr(snap.monthly_net_cash),
            "danger" if snap.monthly_net_cash < ZERO else "success",
            "receipts",
        ),
    )
    notes = (
        snap.golden,
        f"Cause: {snap.known_cause}",
        f"YTD vs plan {vs_plan}  receipts {_inr(snap.fy.receipts)}  payments {_inr(snap.fy.payments)}",
    )
    return MisPack("ceo", "CEO pack", tiles, scorecard(snap)[:3], notes)


def cfo_pack(snap: MisSnapshot) -> MisPack:
    from ssdv.mis.forecast import cash_forecast

    # DuPont: ROE = (Net profit / Sales) * (Sales / Assets) * (Assets / Equity)
    # v1 uses YTD profit as the net-profit component, and current equation assets/equity.
    roe: Decimal | None = None
    if snap.equity != ZERO and snap.fy.sales > ZERO and snap.equation.assets != ZERO:
        profit_margin = snap.ytd_profit / snap.fy.sales
        asset_turnover = snap.fy.sales / snap.equation.assets
        equity_multiplier = snap.equation.assets / snap.equity
        roe = profit_margin * asset_turnover * equity_multiplier

    dso_tone: Tone = "neutral"
    if snap.dso is not None:
        dso_tone = "danger" if snap.dso > DSO_DAYS_MAX else "success"
    ar_tone = _tone_high(snap.metrics.ar_to_sales, AR_TO_SALES_STRESS)
    fc = cash_forecast(snap)
    h30, h60, h90 = fc.horizons
    gst_net_tone: Tone = "warning" if snap.gst_net > ZERO else "neutral"
    tiles = (
        Tile("dso", "DSO (AR / FY sales)", _days(snap.dso), dso_tone, "120000"),
        Tile(
            "roe",
            "DuPont ROE",
            "n/a" if roe is None else _pct(roe, 1),
            "neutral",
            "330000",
        ),
        Tile(
            "dio",
            "DIO (stock / FY COGS)",
            _days(snap.dio),
            "warning" if (snap.dio or 0) > 200 else "neutral",
            "130000",
        ),
        Tile("dpo", "DPO (AP / FY purchases)", _days(snap.dpo), "neutral", "210000"),
        Tile("ccc", "Cash conversion cycle", _days(snap.ccc), "warning", "ccc"),
        Tile("ar", "Trade receivables", _inr(snap.ar), ar_tone, "120000"),
        Tile("ap", "Trade payables", _inr(snap.ap), "neutral", "210000"),
        Tile(
            "msme_43bh",
            "43B(h) MSME overdue risk",
            _inr(snap.msme_43bh_total),
            "danger" if snap.msme_43bh_total > ZERO else "success",
            "msme",
        ),
        Tile("inv", "Inventory (WAC)", _inr(snap.inventory), "neutral", "130000"),
        Tile("gst", "GST net liability", _inr(snap.gst_net), gst_net_tone, "gst"),
        Tile("gst_input", "Input GST", _inr(snap.gst_input), "neutral", "gst_in"),
        Tile("gst_output", "Output GST", _inr(snap.gst_output), "neutral", "gst_out"),
        Tile(
            "od",
            "OD utilisation",
            _pct(snap.od_utilisation, 1),
            "danger" if snap.od_utilisation >= money("0.95") else "warning",
            "113000",
        ),
        Tile("salary", "Salary payable", _inr(snap.salary_payable), "warning", "232000"),
        Tile(
            "cash_30",
            "Cash in 30 days",
            _inr(h30.cash),
            "danger" if h30.cash < ZERO else "success",
            "forecast",
        ),
        Tile(
            "cash_60",
            "Cash in 60 days",
            _inr(h60.cash),
            "danger" if h60.cash < ZERO else "success",
            "forecast",
        ),
        Tile(
            "cash_90",
            "Cash in 90 days",
            _inr(h90.cash),
            "danger" if h90.cash < ZERO else "success",
            "forecast",
        ),
    )
    aging = snap.ar_aging
    notes = (
        snap.golden,
        (
            f"AR aging  0-30 {_inr(aging['0-30'])}  31-60 {_inr(aging['31-60'])}  "
            f"61-90 {_inr(aging['61-90'])}  91-120 {_inr(aging['91-120'])}  "
            f"120+ {_inr(aging['120+'])}  90+ {_inr(aging['90+'])}"
        ),
        (
            f"Banks HDFC {_inr(snap.hdfc)}  ICICI {_inr(snap.icici)}  "
            f"OD {_inr(snap.od)}  limit {_inr(snap.od_limit)}"
        ),
        f"Opex (ex-COGS) {_inr(snap.fy.opex)}  loan {_inr(snap.term_loan)}",
        f"Equation delta {_inr(snap.equation.delta)}  {'holds' if snap.equation.holds else 'BROKEN'}",
        fc.method,
        (
            f"Cash forecast  30 {_inr(h30.cash)}  60 {_inr(h60.cash)}  "
            f"90 {_inr(h90.cash)}  blocked AR 90+ {_inr(fc.blocked_ar)}"
        ),
    )
    return MisPack("cfo", "CFO pack", tiles, scorecard(snap), notes)


def board_pack(snap: MisSnapshot) -> MisPack:
    from ssdv.officemitra.insights import build_red_flags

    rows = scorecard(snap)
    tiles = (
        Tile("assets", "Assets", _inr(snap.equation.assets), "neutral", "tb"),
        Tile("liabilities", "Liabilities", _inr(snap.equation.liabilities), "neutral", "tb"),
        Tile(
            "equity",
            "Equity after close",
            _inr(snap.equity),
            "success" if snap.equity >= ZERO else "danger",
            "330000",
        ),
        Tile(
            "vendor",
            "Top vendor share",
            _pct(snap.metrics.top_vendor_share),
            _tone_high(snap.metrics.top_vendor_share, VENDOR_SHARE_MAX),
            snap.metrics.top_vendor or "vendors",
        ),
        Tile(
            "gm",
            "Gross margin",
            _pct(snap.fy.gm_pct, 1),
            "danger" if snap.metrics.cogs_ratio >= COGS_RATIO_MAX else "success",
            "cogs",
        ),
        Tile("ccc", "Cash conversion cycle", _days(snap.ccc), "warning", "ccc"),
    )
    flags = tuple(item.text for item in build_red_flags(snap))
    notes = (
        snap.golden,
        (
            "Going concern: equity is negative after close when payroll accrues faster than trading gross margin."
            if snap.equity < ZERO
            else "Equity is non-negative after close."
        ),
        f"Signal {'OK' if snap.signal_ok else 'FAIL'} -- {snap.signal_detail}",
        *(flags or ("No Board red flags on DSO policy, cash, equity, or last-month profit.",)),
    )
    return MisPack("board", "Board pack", tiles, rows, notes)


def build_pack(snap: MisSnapshot, pack_id: str) -> MisPack:
    if pack_id == "ceo":
        return ceo_pack(snap)
    if pack_id == "cfo":
        return cfo_pack(snap)
    if pack_id == "board":
        return board_pack(snap)
    raise ValueError(f"Unknown pack {pack_id!r}. Choose ceo, cfo or board.")


def _share_safe(part: Decimal, whole: Decimal) -> Decimal:
    if whole <= ZERO:
        return ZERO
    return (part / whole).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
