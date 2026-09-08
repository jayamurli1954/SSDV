"""Deterministic pack trust signal for OfficeMitra (desktop). No LLM math."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.models import IngestMeta, Voucher
from ssdv.money import ZERO, money
from ssdv.paths import load_yaml
from ssdv.validate import INTEGRITY_GATES, Gate, run_gates

PPT_MIN_SCORE = 70
BUDGET_DEDUCTION = 12
OTHER_GATE_DEDUCTION = 8
INTEGRITY_DEDUCTION = 50


class ExportBlocked(Exception):
    """Board PPT is blocked until books are reviewed and the score is high enough."""


@dataclass(frozen=True)
class QualityReport:
    score: int
    band: str
    imported: bool
    has_budget: bool
    budget_source: str
    sales_budget: Decimal | None
    reviewed: bool
    ppt_allowed: bool
    ppt_block_reason: str | None
    failed_gates: tuple[str, ...]
    breakdown: dict[str, Any]


def budget_sidecar_path(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.stem}.budget.yaml")


def review_sidecar_path(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.stem}.review.json")


def load_budget_sales(db_path: Path, *, fy_code: str | None = None) -> Decimal | None:
    path = budget_sidecar_path(db_path)
    if not path.is_file():
        alt = db_path.with_name(f"{db_path.stem}.budget.yml")
        path = alt if alt.is_file() else path
    if not path.is_file():
        return None
    raw = load_yaml(path)
    if fy_code and isinstance(raw.get("fy"), dict) and fy_code in raw["fy"]:
        return money(raw["fy"][fy_code])
    if raw.get("sales") is not None:
        return money(raw["sales"])
    if raw.get("revenue") is not None:
        return money(raw["revenue"])
    return None


def _voucher_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(Voucher)) or 0)


def _band(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= PPT_MIN_SCORE:
        return "medium"
    return "low"


def score_from_gates(
    gates: list[Gate],
    *,
    imported: bool,
    has_budget: bool,
) -> tuple[int, dict[str, Any]]:
    score = 100
    failed = [g.name for g in gates if not g.ok]
    for name in failed:
        if name in INTEGRITY_GATES:
            score -= INTEGRITY_DEDUCTION
        else:
            score -= OTHER_GATE_DEDUCTION
    missing_budget = imported and not has_budget
    if missing_budget:
        score -= BUDGET_DEDUCTION
    score = max(0, min(100, score))
    breakdown = {
        "gates_total": len(gates),
        "gates_failed": failed,
        "integrity_ok": all(g.ok for g in gates if g.name in INTEGRITY_GATES),
        "missing_budget": missing_budget,
        "imported": imported,
    }
    return score, breakdown


def read_review(db_path: Path, as_of: date, *, voucher_count: int) -> dict[str, Any] | None:
    path = review_sidecar_path(db_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(data.get("as_of") or "") != as_of.isoformat():
        return None
    if int(data.get("voucher_count") or -1) != voucher_count:
        return None
    return data


def mark_reviewed(db_path: Path, as_of: date, *, session: Session) -> dict[str, Any]:
    payload = {
        "as_of": as_of.isoformat(),
        "voucher_count": _voucher_count(session),
        "reviewed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "reviewed_by": "local",
    }
    path = review_sidecar_path(db_path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def assess_session(
    session: Session,
    as_of: date,
    db_path: Path,
    *,
    company: dict | None = None,
    fy_code: str | None = None,
) -> QualityReport:
    gates = run_gates(session, as_of, company=company)
    imported = session.get(IngestMeta, 1) is not None
    sidecar_budget = load_budget_sales(db_path, fy_code=fy_code)
    has_budget = sidecar_budget is not None or not imported
    budget_source = (
        "sidecar" if sidecar_budget is not None else ("company_plan" if not imported else "missing")
    )
    score, breakdown = score_from_gates(gates, imported=imported, has_budget=has_budget)
    reviewed = read_review(db_path, as_of, voucher_count=_voucher_count(session)) is not None
    reason = None
    if score < PPT_MIN_SCORE:
        reason = f"data_quality_score {score} is below {PPT_MIN_SCORE}"
    elif not reviewed:
        reason = "Books are not marked reviewed for this as-of date"
    ppt_allowed = reason is None
    failed = tuple(g.name for g in gates if not g.ok)
    return QualityReport(
        score=score,
        band=_band(score),
        imported=imported,
        has_budget=has_budget,
        budget_source=budget_source,
        sales_budget=sidecar_budget,
        reviewed=reviewed,
        ppt_allowed=ppt_allowed,
        ppt_block_reason=reason,
        failed_gates=failed,
        breakdown=breakdown,
    )


def budget_vs_actual(sales_actual: Decimal, sales_budget: Decimal | None, source: str) -> dict[str, Any]:
    if sales_budget is None:
        return {
            "sales_actual": str(money(sales_actual)),
            "sales_budget": None,
            "variance_abs": None,
            "variance_pct": None,
            "source": source,
        }
    actual = money(sales_actual)
    budget = money(sales_budget)
    variance = money(actual - budget)
    pct = None if budget == ZERO else f"{(variance / budget):.4f}"
    return {
        "sales_actual": str(actual),
        "sales_budget": str(budget),
        "variance_abs": str(variance),
        "variance_pct": pct,
        "source": source,
    }


def enrich_payload(
    payload: dict[str, Any],
    session: Session,
    db_path: Path,
    as_of: date,
    *,
    company: dict | None = None,
) -> dict[str, Any]:
    kpis = payload.get("kpis") or {}
    sales = money(kpis.get("sales") or ZERO)
    fy = payload.get("fy") if isinstance(payload.get("fy"), dict) else {}
    fy_code = str(fy.get("fy_code") or "") or None
    company_plan = money(kpis.get("plan") or ZERO)
    report = assess_session(
        session,
        as_of,
        db_path,
        company=company,
        fy_code=fy_code,
    )
    budget_amount = report.sales_budget
    if budget_amount is None and report.budget_source == "company_plan" and company_plan > ZERO:
        budget_amount = company_plan
    payload["data_quality_score"] = report.score
    payload["data_quality_band"] = report.band
    payload["data_quality_breakdown"] = report.breakdown
    payload["reviewed"] = report.reviewed
    payload["ppt_allowed"] = report.ppt_allowed
    payload["ppt_block_reason"] = report.ppt_block_reason
    payload["budget_vs_actual"] = budget_vs_actual(
        sales, budget_amount, report.budget_source
    )
    return payload


def assert_ppt_allowed(payload: dict[str, Any]) -> None:
    if payload.get("ppt_allowed"):
        return
    reason = str(payload.get("ppt_block_reason") or "Board PPT is blocked")
    raise ExportBlocked(reason)
