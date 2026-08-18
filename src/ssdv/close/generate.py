from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ssdv.close.posting import post_closing, post_depreciation
from ssdv.paths import load_company


def generate_yearend(session: Session, company: dict[str, Any] | None = None) -> tuple[int, int]:
    cfg = company or load_company()
    deps = 0
    closes = 0
    for fy in cfg["calendar"]["fiscal_years"]:
        ending = date.fromisoformat(str(fy["end"]))
        if post_depreciation(session, ending, company=cfg) is not None:
            deps += 1
        if post_closing(session, ending, company=cfg) is not None:
            closes += 1
    return deps, closes
