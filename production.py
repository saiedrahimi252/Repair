# -*- coding: utf-8 -*-
"""ماژول تولید — فاز اول: داشبورد و Master Data پایه."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_connection

production_bp = Blueprint("production", __name__, url_prefix="/production")


def _db():
    return get_connection(session.get("company_db") or "repair")


@production_bp.route("/")
def dashboard():
    db = _db()
    try:
        counts = {}
        for table, key in [
            ("production_products", "products"),
            ("production_stations", "stations"),
            ("production_machines", "machines"),
            ("production_employees", "employees"),
            ("production_shifts", "shifts"),
            ("production_plans", "plans"),
        ]:
            counts[key] = db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        return render_template("production_dashboard.html", counts=counts)
    finally:
        db.close()


@production_bp.route("/products", methods=["GET", "POST"])
def products():
    db = _db()
    try:
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            name = request.form.get("name", "").strip()
            unit = request.form.get("unit", "").strip() or None
            if not code or not name:
                flash("کد و نام محصول الزامی است.", "error")
            else:
                try:
                    db.execute(
                        "INSERT INTO production_products (code,name,unit,is_active) VALUES (?,?,?,1)",
                        (code, name, unit),
                    )
                    db.commit()
                    flash("محصول با موفقیت ثبت شد.", "success")
                except Exception as exc:
                    db.rollback()
                    flash(f"ثبت محصول انجام نشد: {exc}", "error")
            return redirect(url_for("production.products"))
        rows = db.execute(
            "SELECT id,code,name,unit,is_active,created_at FROM production_products ORDER BY name"
        ).fetchall()
        return render_template("production_products.html", rows=rows)
    finally:
        db.close()


@production_bp.route("/stations", methods=["GET", "POST"])
def stations():
    db = _db()
    try:
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            name = request.form.get("name", "").strip()
            stage = request.form.get("stage_name", "").strip() or None
            qty8 = request.form.get("standard_qty_8h", "").strip() or None
            qty1 = request.form.get("standard_qty_1h", "").strip() or None
            cycle = request.form.get("cycle_time_seconds", "").strip() or None
            weight = request.form.get("time_weight", "").strip() or None
            if not code or not name:
                flash("کد و نام ایستگاه الزامی است.", "error")
            else:
                try:
                    db.execute(
                        """INSERT INTO production_stations
                        (code,name,stage_name,standard_qty_8h,standard_qty_1h,cycle_time_seconds,time_weight,is_active)
                        VALUES (?,?,?,?,?,?,?,1)""",
                        (code, name, stage, qty8, qty1, cycle, weight),
                    )
                    db.commit()
                    flash("ایستگاه با موفقیت ثبت شد.", "success")
                except Exception as exc:
                    db.rollback()
                    flash(f"ثبت ایستگاه انجام نشد: {exc}", "error")
            return redirect(url_for("production.stations"))
        rows = db.execute(
            """SELECT id,code,name,stage_name,standard_qty_8h,standard_qty_1h,
                      cycle_time_seconds,time_weight,is_active
               FROM production_stations ORDER BY name"""
        ).fetchall()
        return render_template("production_stations.html", rows=rows)
    finally:
        db.close()
