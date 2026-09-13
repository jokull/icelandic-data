from datetime import date
from scripts.opnirreikningar import coverage_warning


def test_coverage_warning_only_when_range_runs_past_loaded_month():
    assert coverage_warning(date(2026, 8, 31), date(2026, 8, 31)) is None
    assert coverage_warning(date(2026, 6, 30), date(2026, 8, 31)) is None
    w = coverage_warning(date(2026, 12, 31), date(2026, 8, 31))
    assert w and "2026-08-31" in w and "incomplete" in w
