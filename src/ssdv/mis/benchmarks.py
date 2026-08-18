from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from ssdv.mis.kpis import MisSnapshot
from ssdv.mis.policy import (
    COGS_RATIO_MAX,
    COLLECTION_EFFICIENCY_MIN,
    CUSTOMER_SHARE_MAX,
    DSO_DAYS_MAX,
    INVENTORY_TO_SALES_MAX,
)
from ssdv.money import ZERO, money
from ssdv.paths import default_db_path, load_company

PEER_NAME = "ABC trading baseline"
BENCHMARK_SOURCE = (
    "SSDV policy bands for these trading books. "
    "Peer is ABC Industrial generated baseline (data/ssdv.sqlite) when that vault exists. "
    "Not a surveyed industry average."
)
_CURRENT_RATIO_MIN = money("1")
_GM_PCT_MIN = money(1) - COGS_RATIO_MAX


@dataclass(frozen=True)
class BenchmarkRow:
    id: str
    name: str
    actual: str
    policy: str
    peer: str
    policy_status: str
    vs_peer: str
    tone: str


def _dec(value: Decimal | int | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def _pct(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"{(value * 100):.1f}%"


def _days(value: int | None) -> str:
    return "n/a" if value is None else f"{value} d"


def _times(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}x"


def _rate_high(actual: Decimal | None, floor: Decimal) -> tuple[str, str]:
    if actual is None:
        return "n/a", "neutral"
    if actual < floor:
        return "Breach", "danger"
    return "Hold", "success"


def _rate_low(actual: Decimal | int | None, ceiling: Decimal | int) -> tuple[str, str]:
    if actual is None:
        return "n/a", "neutral"
    if Decimal(actual) > Decimal(ceiling):
        return "Breach", "danger"
    return "Hold", "success"


def _vs_peer(
    actual: Decimal | int | None,
    peer: Decimal | int | None,
    *,
    higher_is_better: bool,
) -> str:
    if actual is None or peer is None:
        return "No ABC baseline vault"
    left = Decimal(actual)
    right = Decimal(peer)
    if left == right:
        return f"Same as {PEER_NAME}"
    better = left > right if higher_is_better else left < right
    return f"Better than {PEER_NAME}" if better else f"Worse than {PEER_NAME}"


def _row(
    *,
    id: str,
    name: str,
    actual: str,
    policy: str,
    peer: str,
    status: str,
    tone: str,
    vs_peer: str,
) -> BenchmarkRow:
    return BenchmarkRow(
        id=id,
        name=name,
        actual=actual,
        policy=policy,
        peer=peer,
        policy_status=status,
        vs_peer=vs_peer,
        tone=tone,
    )


def build_benchmarks(
    snap: MisSnapshot,
    peer: MisSnapshot | None = None,
) -> tuple[BenchmarkRow, ...]:
    """Rate posted KPIs vs SSDV policy. Optional peer is ABC baseline, not industry."""
    gm_status, gm_tone = _rate_high(snap.fy.gm_pct, _GM_PCT_MIN)
    dso_status, dso_tone = _rate_low(snap.dso, DSO_DAYS_MAX)
    coll_status, coll_tone = _rate_high(snap.collection_efficiency, COLLECTION_EFFICIENCY_MIN)
    cr_status, cr_tone = _rate_high(snap.current_ratio, _CURRENT_RATIO_MIN)
    qr_status, qr_tone = _rate_high(snap.quick_ratio, _CURRENT_RATIO_MIN)
    inv_status, inv_tone = _rate_low(snap.metrics.inventory_to_sales, INVENTORY_TO_SALES_MAX)
    cust_status, cust_tone = _rate_low(snap.metrics.top_customer_share, CUSTOMER_SHARE_MAX)
    cogs_status, cogs_tone = _rate_low(snap.metrics.cogs_ratio, COGS_RATIO_MAX)

    peer_gm = peer.fy.gm_pct if peer is not None else None
    peer_dso = peer.dso if peer is not None else None
    peer_coll = peer.collection_efficiency if peer is not None else None
    peer_cr = peer.current_ratio if peer is not None else None
    peer_qr = peer.quick_ratio if peer is not None else None
    peer_inv = peer.metrics.inventory_to_sales if peer is not None else None
    peer_cust = peer.metrics.top_customer_share if peer is not None else None
    peer_ccc = peer.ccc if peer is not None else None
    peer_cogs = peer.metrics.cogs_ratio if peer is not None else None

    ccc_status, ccc_tone = "n/a", "neutral"
    if snap.ccc is not None and peer_ccc is not None:
        ccc_status = "Hold"
        ccc_tone = "success" if snap.ccc <= peer_ccc else "warning"

    return (
        _row(
            id="gross_margin",
            name="Gross margin",
            actual=_pct(snap.fy.gm_pct),
            policy=f"at least {_pct(_GM_PCT_MIN)}",
            peer=_pct(peer_gm),
            status=gm_status,
            tone=gm_tone,
            vs_peer=_vs_peer(snap.fy.gm_pct, peer_gm, higher_is_better=True),
        ),
        _row(
            id="cogs_ratio",
            name="COGS / sales",
            actual=f"{snap.metrics.cogs_ratio:.2f}",
            policy=f"under {COGS_RATIO_MAX:.2f}",
            peer=f"{peer_cogs:.2f}" if peer_cogs is not None else "n/a",
            status=cogs_status,
            tone=cogs_tone,
            vs_peer=_vs_peer(snap.metrics.cogs_ratio, peer_cogs, higher_is_better=False),
        ),
        _row(
            id="dso",
            name="DSO",
            actual=_days(snap.dso),
            policy=f"under {DSO_DAYS_MAX} days",
            peer=_days(peer_dso),
            status=dso_status,
            tone=dso_tone,
            vs_peer=_vs_peer(_dec(snap.dso), _dec(peer_dso), higher_is_better=False),
        ),
        _row(
            id="collection_efficiency",
            name="Collection efficiency",
            actual=_pct(snap.collection_efficiency),
            policy=f"at least {_pct(COLLECTION_EFFICIENCY_MIN)}",
            peer=_pct(peer_coll),
            status=coll_status,
            tone=coll_tone,
            vs_peer=_vs_peer(snap.collection_efficiency, peer_coll, higher_is_better=True),
        ),
        _row(
            id="current_ratio",
            name="Current ratio",
            actual=_times(snap.current_ratio),
            policy=f"at least {_times(_CURRENT_RATIO_MIN)}",
            peer=_times(peer_cr),
            status=cr_status,
            tone=cr_tone,
            vs_peer=_vs_peer(snap.current_ratio, peer_cr, higher_is_better=True),
        ),
        _row(
            id="quick_ratio",
            name="Quick ratio",
            actual=_times(snap.quick_ratio),
            policy=f"at least {_times(_CURRENT_RATIO_MIN)}",
            peer=_times(peer_qr),
            status=qr_status,
            tone=qr_tone,
            vs_peer=_vs_peer(snap.quick_ratio, peer_qr, higher_is_better=True),
        ),
        _row(
            id="inventory_to_sales",
            name="Inventory / sales",
            actual=f"{snap.metrics.inventory_to_sales:.2f}",
            policy=f"under {INVENTORY_TO_SALES_MAX:.2f}",
            peer=f"{peer_inv:.2f}" if peer_inv is not None else "n/a",
            status=inv_status,
            tone=inv_tone,
            vs_peer=_vs_peer(snap.metrics.inventory_to_sales, peer_inv, higher_is_better=False),
        ),
        _row(
            id="customer_share",
            name="Top customer share",
            actual=_pct(snap.metrics.top_customer_share),
            policy=f"under {_pct(CUSTOMER_SHARE_MAX)}",
            peer=_pct(peer_cust),
            status=cust_status,
            tone=cust_tone,
            vs_peer=_vs_peer(snap.metrics.top_customer_share, peer_cust, higher_is_better=False),
        ),
        _row(
            id="ccc",
            name="Cash conversion cycle",
            actual=_days(snap.ccc),
            policy="no SSDV day cap",
            peer=_days(peer_ccc),
            status=ccc_status,
            tone=ccc_tone,
            vs_peer=_vs_peer(_dec(snap.ccc), _dec(peer_ccc), higher_is_better=False),
        ),
    )


def load_baseline_peer(as_of: date, *, exclude: Path | None = None) -> MisSnapshot | None:
    """Read ABC generated baseline. Returns None if missing, not baseline, or same file."""
    from ssdv.db import create_schema, make_engine, session_scope
    from ssdv.mis.kpis import mis_snapshot

    path = default_db_path()
    if not path.exists():
        return None
    if exclude is not None and path.resolve() == Path(exclude).resolve():
        return None
    cfg = load_company()
    books_end = date.fromisoformat(str(cfg["calendar"]["books_end"]))
    peer_as_of = min(as_of, books_end)
    engine = make_engine(path)
    create_schema(engine)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, peer_as_of)
    if snap.scenario_id != "baseline":
        return None
    if snap.fy.sales <= ZERO:
        return None
    return snap
