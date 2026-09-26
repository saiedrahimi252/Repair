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


def test_shift_window_normal_shift():
    from datetime import date, time
    from production import _shift_window

    start, end = _shift_window(date(2026, 9, 26), time(8, 0), time(16, 0), False)
    assert start.isoformat() == "2026-09-26T08:00:00"
    assert end.isoformat() == "2026-09-26T16:00:00"


def test_shift_window_crosses_midnight():
    from datetime import date, time
    from production import _shift_window

    start, end = _shift_window(date(2026, 9, 26), time(22, 0), time(6, 0), True)
    assert start.isoformat() == "2026-09-26T22:00:00"
    assert end.isoformat() == "2026-09-27T06:00:00"


def test_stop_minutes_use_planned_window_and_ignore_late_stop():
    from datetime import date, datetime, time
    from production import _stop_minutes_for_calendar_row

    class FakeDB:
        def execute(self, sql, params):
            class Result:
                def fetchone(self):
                    return {
                        "start_time": time(8, 0),
                        "end_time": time(16, 0),
                        "crosses_midnight": False,
                    }

                def fetchall(self):
                    return [
                        {
                            "start_at": datetime(2026, 9, 26, 9, 0),
                            "end_at": datetime(2026, 9, 26, 10, 0),
                            "machine_id": None,
                            "counts_as_unavailability": True,
                            "is_planned_stop": False,
                        },
                        {
                            "start_at": datetime(2026, 9, 26, 15, 30),
                            "end_at": datetime(2026, 9, 26, 16, 30),
                            "machine_id": None,
                            "counts_as_unavailability": True,
                            "is_planned_stop": False,
                        },
                    ]

            return Result()

    result = _stop_minutes_for_calendar_row(
        FakeDB(), date(2026, 9, 26), 1, 1, 480
    )
    assert result["unavailability_minutes"] == 90.0
    assert result["stop_minutes"] == 90.0


def test_stop_minutes_include_after_midnight_inside_cross_midnight_shift():
    from datetime import date, datetime, time
    from production import _stop_minutes_for_calendar_row

    class FakeDB:
        def execute(self, sql, params):
            class Result:
                def fetchone(self):
                    return {
                        "start_time": time(22, 0),
                        "end_time": time(6, 0),
                        "crosses_midnight": True,
                    }

                def fetchall(self):
                    return [
                        {
                            "start_at": datetime(2026, 9, 27, 1, 0),
                            "end_at": datetime(2026, 9, 27, 2, 30),
                            "machine_id": None,
                            "counts_as_unavailability": True,
                            "is_planned_stop": False,
                        }
                    ]

            return Result()

    result = _stop_minutes_for_calendar_row(
        FakeDB(), date(2026, 9, 26), 1, 1, 480
    )
    assert result["unavailability_minutes"] == 90.0
    assert result["stop_minutes"] == 90.0



def test_merge_intervals_deduplicates_overlapping_machine_stops():
    from datetime import datetime, timedelta
    from production import _merged_interval_minutes

    base = datetime(2026, 9, 26, 8, 0)
    # Machine A: 08:00-09:00, Machine B: 08:30-09:30.
    # Station downtime must count the union once: 90 minutes.
    assert _merged_interval_minutes([
        (base, base + timedelta(minutes=60)),
        (base + timedelta(minutes=30), base + timedelta(minutes=90)),
    ]) == 90.0


def test_merge_intervals_deduplicates_station_wide_and_machine_stop():
    from datetime import datetime, timedelta
    from production import _merged_interval_minutes

    base = datetime(2026, 9, 26, 10, 0)
    # Station-wide stop overlaps a machine-specific stop.
    assert _merged_interval_minutes([
        (base, base + timedelta(minutes=45)),
        (base + timedelta(minutes=15), base + timedelta(minutes=30)),
    ]) == 45.0


def test_stop_minutes_excludes_planned_overlap_from_unavailability():
    from datetime import date, datetime, time
    from production import _stop_minutes_for_calendar_row

    class FakeDB:
        def execute(self, sql, params):
            class Result:
                def fetchone(self):
                    return {
                        "start_time": time(8, 0),
                        "end_time": time(16, 0),
                        "crosses_midnight": False,
                    }

                def fetchall(self):
                    return [
                        {
                            "start_at": datetime(2026, 9, 26, 10, 0),
                            "end_at": datetime(2026, 9, 26, 11, 0),
                            "machine_id": None,
                            "counts_as_unavailability": True,
                            "is_planned_stop": True,
                        },
                        {
                            "start_at": datetime(2026, 9, 26, 10, 30),
                            "end_at": datetime(2026, 9, 26, 11, 30),
                            "machine_id": None,
                            "counts_as_unavailability": True,
                            "is_planned_stop": False,
                        },
                    ]

            return Result()

    result = _stop_minutes_for_calendar_row(
        FakeDB(), date(2026, 9, 26), 1, 1, 480
    )
    assert result["planned_stop_minutes"] == 60.0
    assert result["unavailability_minutes"] == 30.0
    assert result["stop_minutes"] == 90.0


def test_stop_minutes_clips_to_short_planned_window():
    from datetime import date, datetime, time
    from production import _stop_minutes_for_calendar_row

    class FakeDB:
        def execute(self, sql, params):
            class Result:
                def fetchone(self):
                    return {
                        "start_time": time(8, 0),
                        "end_time": time(16, 0),
                        "crosses_midnight": False,
                    }

                def fetchall(self):
                    return [
                        {
                            "start_at": datetime(2026, 9, 26, 11, 0),
                            "end_at": datetime(2026, 9, 26, 13, 0),
                            "machine_id": None,
                            "counts_as_unavailability": True,
                            "is_planned_stop": False,
                        }
                    ]

            return Result()

    # Planned window is 08:00-12:00, so only 11:00-12:00 counts.
    result = _stop_minutes_for_calendar_row(
        FakeDB(), date(2026, 9, 26), 1, 1, 240
    )
    assert result["unavailability_minutes"] == 60.0
    assert result["stop_minutes"] == 60.0


def test_stop_minutes_union_handles_nested_and_chain_overlaps():
    from datetime import date, datetime, time
    from production import _stop_minutes_for_calendar_row

    class FakeDB:
        def execute(self, sql, params):
            class Result:
                def fetchone(self):
                    return {
                        "start_time": time(8, 0),
                        "end_time": time(16, 0),
                        "crosses_midnight": False,
                    }

                def fetchall(self):
                    base = datetime(2026, 9, 26, 8, 0)
                    return [
                        {"start_at": base, "end_at": datetime(2026, 9, 26, 10, 0), "machine_id": 1, "counts_as_unavailability": True, "is_planned_stop": False},
                        {"start_at": datetime(2026, 9, 26, 8, 30), "end_at": datetime(2026, 9, 26, 9, 0), "machine_id": 2, "counts_as_unavailability": True, "is_planned_stop": False},
                        {"start_at": datetime(2026, 9, 26, 9, 45), "end_at": datetime(2026, 9, 26, 10, 30), "machine_id": 3, "counts_as_unavailability": True, "is_planned_stop": False},
                    ]

            return Result()

    result = _stop_minutes_for_calendar_row(
        FakeDB(), date(2026, 9, 26), 1, 1, 480
    )
    # 08:00-10:30 is one chained union.
    assert result["unavailability_minutes"] == 150.0
    assert result["stop_minutes"] == 150.0


def test_stop_counts_as_unavailability_excludes_planned_stop():
    from production import _stop_counts_as_unavailability

    assert _stop_counts_as_unavailability({"counts_as_unavailability": True, "is_planned_stop": False}) is True
    assert _stop_counts_as_unavailability({"counts_as_unavailability": True, "is_planned_stop": True}) is False
    assert _stop_counts_as_unavailability({"counts_as_unavailability": False, "is_planned_stop": False}) is False
