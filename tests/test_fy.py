from datetime import date

from ssdv.fy import fy_code, fy_end, fy_month, fy_start, iter_month_ends, month_key, month_label


def test_fy_code_april_starts_new_year() -> None:
    assert fy_code(date(2023, 4, 1)) == "FY2023-24"
    assert fy_code(date(2024, 3, 31)) == "FY2023-24"
    assert fy_code(date(2024, 4, 1)) == "FY2024-25"


def test_fy_bounds() -> None:
    d = date(2025, 8, 13)
    assert fy_start(d) == date(2025, 4, 1)
    assert fy_end(d) == date(2026, 3, 31)
    assert fy_month(d) == 5
    assert fy_month(date(2026, 3, 1)) == 12


def test_month_key_and_label() -> None:
    assert month_key(date(2023, 4, 1)) == "2023-04"
    assert month_label(date(2023, 4, 15)) == "Apr-23"
    assert month_label(date(2026, 3, 31)) == "Mar-26"
    ends = iter_month_ends(date(2023, 4, 1), date(2024, 3, 31))
    assert len(ends) == 12
    assert month_key(ends[0]) == "2023-04"
    assert month_key(ends[-1]) == "2024-03"
