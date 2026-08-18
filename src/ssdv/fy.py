from __future__ import annotations

from datetime import date, timedelta

_FY_START_MONTH = 4
_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def fy_code(d: date) -> str:
    if d.month >= _FY_START_MONTH:
        start_year = d.year
    else:
        start_year = d.year - 1
    end_yy = str(start_year + 1)[-2:]
    return f"FY{start_year}-{end_yy}"


def fy_start(d: date) -> date:
    if d.month >= _FY_START_MONTH:
        return date(d.year, 4, 1)
    return date(d.year - 1, 4, 1)


def fy_end(d: date) -> date:
    start = fy_start(d)
    return date(start.year + 1, 3, 31)


def fy_month(d: date) -> int:
    """1 = April … 12 = March."""
    if d.month >= _FY_START_MONTH:
        return d.month - 3
    return d.month + 9


def month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    first_next = date(d.year, d.month + 1, 1)
    return first_next - timedelta(days=1)


def iter_month_ends(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    out: list[date] = []
    while cursor <= last:
        out.append(month_end(cursor))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return out


def month_key(d: date) -> str:
    """ISO year-month, e.g. 2023-04."""
    return f"{d.year:04d}-{d.month:02d}"


def month_label(d: date) -> str:
    """Chart label, e.g. Apr-23. English abbreviations, not locale strftime."""
    return f"{_MONTH_ABBR[d.month - 1]}-{str(d.year)[-2:]}"
