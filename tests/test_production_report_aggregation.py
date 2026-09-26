# -*- coding: utf-8 -*-
"""Regression tests for production-report aggregation semantics.

These tests exercise the same aggregation shape used by the OEE report:
approved plans only, grouping by plan_item_id, and exclusion of orphan events.
"""

import sqlite3


PRODUCTION_AGGREGATION_SQL = """
    SELECT COALESCE(SUM(q.qty),0) AS qty
    FROM (
        SELECT e.plan_item_id, SUM(e.quantity) AS qty
        FROM production_entries e
        JOIN production_plan_items i ON i.id=e.plan_item_id
        JOIN production_plans p ON p.id=i.plan_id AND p.status='approved'
        WHERE e.production_date=?
          AND e.shift_id=?
          AND i.work_day=?
          AND i.station_id=?
          AND i.product_id=?
        GROUP BY e.plan_item_id
    ) q
"""


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE production_plans (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL
        );
        CREATE TABLE production_plan_items (
            id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            work_day TEXT NOT NULL,
            station_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL
        );
        CREATE TABLE production_entries (
            id INTEGER PRIMARY KEY,
            plan_item_id INTEGER,
            production_date TEXT NOT NULL,
            shift_id INTEGER NOT NULL,
            quantity REAL NOT NULL
        );
        """
    )
    return db


def _query_qty(db, product_id=10):
    return db.execute(
        PRODUCTION_AGGREGATION_SQL,
        ("2026-09-26", 1, "2026-09-26", 5, product_id),
    ).fetchone()["qty"]


def test_report_aggregation_ignores_non_approved_plan_entries():
    db = _db()
    db.executemany(
        "INSERT INTO production_plans(id,status) VALUES (?,?)",
        [(1, "approved"), (2, "draft")],
    )
    db.executemany(
        """INSERT INTO production_plan_items
           (id,plan_id,work_day,station_id,product_id)
           VALUES (?,?,?,?,?)""",
        [(101, 1, "2026-09-26", 5, 10), (102, 2, "2026-09-26", 5, 10)],
    )
    db.executemany(
        """INSERT INTO production_entries
           (id,plan_item_id,production_date,shift_id,quantity)
           VALUES (?,?,?,?,?)""",
        [(1, 101, "2026-09-26", 1, 40), (2, 102, "2026-09-26", 1, 999)],
    )

    assert _query_qty(db) == 40


def test_report_aggregation_sums_multiple_plan_items_without_double_counting():
    db = _db()
    db.execute("INSERT INTO production_plans(id,status) VALUES (1,'approved')")
    db.executemany(
        """INSERT INTO production_plan_items
           (id,plan_id,work_day,station_id,product_id)
           VALUES (?,?,?,?,?)""",
        [
            (101, 1, "2026-09-26", 5, 10),
            (102, 1, "2026-09-26", 5, 10),
        ],
    )
    db.executemany(
        """INSERT INTO production_entries
           (id,plan_item_id,production_date,shift_id,quantity)
           VALUES (?,?,?,?,?)""",
        [
            (1, 101, "2026-09-26", 1, 40),
            (2, 101, "2026-09-26", 1, 10),
            (3, 102, "2026-09-26", 1, 25),
        ],
    )

    # 50 from item 101 + 25 from item 102; no many-to-many multiplication.
    assert _query_qty(db) == 75


def test_report_aggregation_excludes_event_without_plan_item_id():
    db = _db()
    db.execute("INSERT INTO production_plans(id,status) VALUES (1,'approved')")
    db.execute(
        """INSERT INTO production_plan_items
           (id,plan_id,work_day,station_id,product_id)
           VALUES (101,1,'2026-09-26',5,10)"""
    )
    db.executemany(
        """INSERT INTO production_entries
           (id,plan_item_id,production_date,shift_id,quantity)
           VALUES (?,?,?,?,?)""",
        [
            (1, 101, "2026-09-26", 1, 40),
            (2, None, "2026-09-26", 1, 700),
        ],
    )

    assert _query_qty(db) == 40


def test_report_aggregation_does_not_mix_product_or_station():
    db = _db()
    db.execute("INSERT INTO production_plans(id,status) VALUES (1,'approved')")
    db.executemany(
        """INSERT INTO production_plan_items
           (id,plan_id,work_day,station_id,product_id)
           VALUES (?,?,?,?,?)""",
        [
            (101, 1, "2026-09-26", 5, 10),
            (102, 1, "2026-09-26", 6, 10),
            (103, 1, "2026-09-26", 5, 11),
        ],
    )
    db.executemany(
        """INSERT INTO production_entries
           (id,plan_item_id,production_date,shift_id,quantity)
           VALUES (?,?,?,?,?)""",
        [
            (1, 101, "2026-09-26", 1, 40),
            (2, 102, "2026-09-26", 1, 500),
            (3, 103, "2026-09-26", 1, 600),
        ],
    )

    assert _query_qty(db, product_id=10) == 40


WASTE_AGGREGATION_SQL = """
    SELECT COALESCE(SUM(q.waste_qty),0) AS waste_qty,
           COALESCE(SUM(q.rework_qty),0) AS rework_qty
    FROM (
        SELECT w.plan_item_id,
               SUM(CASE WHEN w.record_type='waste' THEN w.quantity ELSE 0 END) AS waste_qty,
               SUM(CASE WHEN w.record_type='rework' THEN w.quantity ELSE 0 END) AS rework_qty
        FROM production_waste_entries w
        JOIN production_plan_items i ON i.id=w.plan_item_id
        JOIN production_plans p ON p.id=i.plan_id AND p.status='approved'
        WHERE w.production_date=?
          AND w.shift_id=?
          AND i.work_day=?
          AND i.station_id=?
          AND i.product_id=?
        GROUP BY w.plan_item_id
    ) q
"""


def _waste_db():
    db = _db()
    db.execute("""
        CREATE TABLE production_waste_entries (
            id INTEGER PRIMARY KEY,
            plan_item_id INTEGER,
            production_date TEXT NOT NULL,
            shift_id INTEGER NOT NULL,
            record_type TEXT NOT NULL,
            quantity REAL NOT NULL
        )
    """)
    return db


def _query_waste(db, product_id=10):
    return db.execute(
        WASTE_AGGREGATION_SQL,
        ("2026-09-26", 1, "2026-09-26", 5, product_id),
    ).fetchone()


def test_report_waste_aggregation_ignores_non_approved_plan_entries():
    db = _waste_db()
    db.executemany(
        "INSERT INTO production_plans(id,status) VALUES (?,?)",
        [(1, "approved"), (2, "draft")],
    )
    db.executemany(
        """INSERT INTO production_plan_items
           (id,plan_id,work_day,station_id,product_id)
           VALUES (?,?,?,?,?)""",
        [(101, 1, "2026-09-26", 5, 10), (102, 2, "2026-09-26", 5, 10)],
    )
    db.executemany(
        """INSERT INTO production_waste_entries
           (id,plan_item_id,production_date,shift_id,record_type,quantity)
           VALUES (?,?,?,?,?,?)""",
        [
            (1, 101, "2026-09-26", 1, "waste", 4),
            (2, 101, "2026-09-26", 1, "rework", 3),
            (3, 102, "2026-09-26", 1, "waste", 999),
        ],
    )

    row = _query_waste(db)
    assert row["waste_qty"] == 4
    assert row["rework_qty"] == 3


def test_report_waste_aggregation_sums_multiple_plan_items_without_double_counting():
    db = _waste_db()
    db.execute("INSERT INTO production_plans(id,status) VALUES (1,'approved')")
    db.executemany(
        """INSERT INTO production_plan_items
           (id,plan_id,work_day,station_id,product_id)
           VALUES (?,?,?,?,?)""",
        [
            (101, 1, "2026-09-26", 5, 10),
            (102, 1, "2026-09-26", 5, 10),
        ],
    )
    db.executemany(
        """INSERT INTO production_waste_entries
           (id,plan_item_id,production_date,shift_id,record_type,quantity)
           VALUES (?,?,?,?,?,?)""",
        [
            (1, 101, "2026-09-26", 1, "waste", 4),
            (2, 101, "2026-09-26", 1, "rework", 2),
            (3, 102, "2026-09-26", 1, "waste", 5),
            (4, 102, "2026-09-26", 1, "rework", 1),
        ],
    )

    row = _query_waste(db)
    assert row["waste_qty"] == 9
    assert row["rework_qty"] == 3


def test_report_waste_aggregation_excludes_event_without_plan_item_id():
    db = _waste_db()
    db.execute("INSERT INTO production_plans(id,status) VALUES (1,'approved')")
    db.execute(
        """INSERT INTO production_plan_items
           (id,plan_id,work_day,station_id,product_id)
           VALUES (101,1,'2026-09-26',5,10)"""
    )
    db.executemany(
        """INSERT INTO production_waste_entries
           (id,plan_item_id,production_date,shift_id,record_type,quantity)
           VALUES (?,?,?,?,?,?)""",
        [
            (1, 101, "2026-09-26", 1, "waste", 4),
            (2, None, "2026-09-26", 1, "waste", 700),
        ],
    )

    row = _query_waste(db)
    assert row["waste_qty"] == 4
    assert row["rework_qty"] == 0
