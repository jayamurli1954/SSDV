from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ssdv.paths import load_company, load_yaml, repo_root


def load_holidays(company: dict[str, Any] | None = None) -> set[date]:
    cfg = company or load_company()
    path = repo_root() / str(cfg["generator"]["holidays_file"])
    payload = load_yaml(path)
    out: set[date] = set()
    for raw in payload.get("holidays", []):
        if isinstance(raw, date):
            out.add(raw)
        else:
            out.add(date.fromisoformat(str(raw)))
    return out


def working_days(
    start: date,
    end: date,
    *,
    skip_sundays: bool = True,
    holidays: set[date] | None = None,
) -> list[date]:
    holidays = holidays or set()
    days: list[date] = []
    cursor = start
    one = timedelta(days=1)
    while cursor <= end:
        if not (skip_sundays and cursor.weekday() == 6) and cursor not in holidays:
            days.append(cursor)
        cursor += one
    return days


def next_working_day(
    start: date,
    end: date,
    *,
    skip_sundays: bool = True,
    holidays: set[date] | None = None,
) -> date | None:
    holidays = holidays or set()
    cursor = start
    one = timedelta(days=1)
    while cursor <= end:
        if not (skip_sundays and cursor.weekday() == 6) and cursor not in holidays:
            return cursor
        cursor += one
    return None


def previous_working_day(
    start: date,
    *,
    skip_sundays: bool = True,
    holidays: set[date] | None = None,
) -> date:
    holidays = holidays or set()
    cursor = start
    one = timedelta(days=1)
    for _ in range(31):
        if not (skip_sundays and cursor.weekday() == 6) and cursor not in holidays:
            return cursor
        cursor -= one
    return start
