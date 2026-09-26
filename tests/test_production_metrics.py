from datetime import datetime, date, time
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from production import (
    _merge_intervals,
    _subtract_intervals,
    _merged_interval_minutes,
    _calculate_quality,
    _calculate_performance,
    _calculate_oee,
    _shift_window,
)


def dt(h, m=0, day=1):
    return datetime(2026, 9, day, h, m)


def test_merge_intervals_merges_overlap_and_touching_ranges():
    assert _merge_intervals([(dt(8), dt(9)), (dt(8, 30), dt(10)), (dt(10), dt(11))]) == [
        (dt(8), dt(11))
    ]


def test_merge_intervals_ignores_empty_or_reverse_ranges():
    assert _merge_intervals([(dt(8), dt(8)), (dt(9), dt(8)), (dt(10), dt(11))]) == [
        (dt(10), dt(11))
    ]


def test_subtract_intervals_removes_planned_overlap_from_unavailability():
    result = _subtract_intervals(
        [(dt(8), dt(10))],
        [(dt(8, 30), dt(9, 30))],
    )
    assert result == [(dt(8), dt(8, 30)), (dt(9, 30), dt(10))]


def test_merged_interval_minutes_does_not_double_count_overlap():
    assert _merged_interval_minutes([(dt(8), dt(9)), (dt(8, 30), dt(9, 30))]) == 90.0


def test_quality_uses_waste_and_rework():
    assert _calculate_quality(100, 10, 5) == 85.0


def test_quality_rejects_invalid_negative_inputs_and_zero_production():
    assert _calculate_quality(-1, 0, 0) is None
    assert _calculate_quality(100, -1, 0) is None
    assert _calculate_quality(100, 0, -1) is None
    assert _calculate_quality(0, 0, 0) is None


def test_quality_rejects_non_finite_values():
    assert _calculate_quality(math.inf, 0, 0) is None
    assert _calculate_quality(100, math.nan, 0) is None


def test_performance_calculation_and_cap():
    assert _calculate_performance(60, 60, 60) == 100.0
    assert _calculate_performance(120, 60, 60) == 100.0


def test_performance_rejects_non_positive_production():
    assert _calculate_performance(0, 60, 60) is None
    assert _calculate_performance(-1, 60, 60) is None


def test_performance_rejects_invalid_cycle_or_available_time():
    assert _calculate_performance(10, 0, 60) is None
    assert _calculate_performance(10, -1, 60) is None
    assert _calculate_performance(10, 60, 0) is None
    assert _calculate_performance(10, 60, -1) is None


def test_performance_rejects_negative_or_non_finite_production():
    assert _calculate_performance(-1, 60, 60) is None
    assert _calculate_performance(math.inf, 60, 60) is None


def test_oee_requires_all_three_components():
    assert _calculate_oee(90, 80, 95) == 68.4
    assert _calculate_oee(None, 80, 95) is None
    assert _calculate_oee(90, None, 95) is None
    assert _calculate_oee(90, 80, None) is None


def test_oee_rejects_negative_or_non_finite_components():
    assert _calculate_oee(-1, 80, 95) is None
    assert _calculate_oee(90, math.inf, 95) is None


def test_shift_window_normal_shift():
    start, end = _shift_window(date(2026, 9, 26), time(8), time(16), False)
    assert start == datetime(2026, 9, 26, 8)
    assert end == datetime(2026, 9, 26, 16)


def test_shift_window_crosses_midnight():
    start, end = _shift_window(date(2026, 9, 26), time(22), time(6), True)
    assert start == datetime(2026, 9, 26, 22)
    assert end == datetime(2026, 9, 27, 6)
