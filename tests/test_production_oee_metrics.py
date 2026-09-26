# -*- coding: utf-8 -*-
"""Unit tests for production OEE metric helpers."""

import math

from production import _calculate_oee, _calculate_performance, _calculate_quality


def test_quality_basic():
    assert _calculate_quality(100, 5, 10) == 85.0


def test_quality_never_negative():
    assert _calculate_quality(100, 120, 5) == 0.0


def test_quality_zero_production_is_not_zero():
    assert _calculate_quality(0, 0, 0) is None


def test_quality_rejects_non_finite():
    assert _calculate_quality(float("nan"), 0, 0) is None
    assert _calculate_quality(100, float("inf"), 0) is None


def test_performance_basic():
    # 100 units × 30 sec = 3000 sec over 60 min = 83.333...%
    result = _calculate_performance(100, 30, 60)
    assert math.isclose(result, 83.3333333333, rel_tol=1e-9)


def test_performance_is_capped_at_100():
    assert _calculate_performance(200, 60, 60) == 100.0


def test_performance_requires_valid_cycle_time_and_available_time():
    assert _calculate_performance(100, 0, 60) is None
    assert _calculate_performance(100, -1, 60) is None
    assert _calculate_performance(100, 30, 0) is None


def test_performance_rejects_non_finite():
    assert _calculate_performance(100, float("nan"), 60) is None
    assert _calculate_performance(100, 30, float("inf")) is None


def test_oee_requires_all_components():
    assert _calculate_oee(90, None, 95) is None
    assert _calculate_oee(None, 90, 95) is None


def test_oee_basic():
    # 90% × 80% × 95% = 68.4%
    assert math.isclose(_calculate_oee(90, 80, 95), 68.4, rel_tol=1e-9)


def test_oee_is_capped_at_100():
    assert _calculate_oee(110, 110, 110) == 100.0


def test_quality_rejects_negative_waste_or_rework():
    assert _calculate_quality(100, -1, 0) is None
    assert _calculate_quality(100, 0, -1) is None


def test_quality_rejects_negative_production():
    assert _calculate_quality(-1, 0, 0) is None


def test_subtract_intervals_removes_planned_overlap():
    from production import _subtract_intervals
    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, 8, 0)
    assert _subtract_intervals(
        [(base, base + timedelta(minutes=60))],
        [(base + timedelta(minutes=20), base + timedelta(minutes=40))],
    ) == [
        (base, base + timedelta(minutes=20)),
        (base + timedelta(minutes=40), base + timedelta(minutes=60)),
    ]


def test_subtract_intervals_handles_multiple_blockers():
    from production import _subtract_intervals
    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, 8, 0)
    assert _subtract_intervals(
        [(base, base + timedelta(minutes=60))],
        [
            (base + timedelta(minutes=10), base + timedelta(minutes=20)),
            (base + timedelta(minutes=30), base + timedelta(minutes=45)),
        ],
    ) == [
        (base, base + timedelta(minutes=10)),
        (base + timedelta(minutes=20), base + timedelta(minutes=30)),
        (base + timedelta(minutes=45), base + timedelta(minutes=60)),
    ]
