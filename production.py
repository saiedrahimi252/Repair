# -*- coding: utf-8 -*-
"""ماژول تولید — فاز اول: داشبورد و Master Data پایه."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_connection
from auth import roles_required

production_bp = Blueprint("production", __name__, url_prefix="/production")


def _db():
    return get_connection(session.get("company_db") or "repair")


@production_bp.route("/")
@roles_required("admin")
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
@roles_required("admin")
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
@roles_required("admin")
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


@production_bp.route("/machines", methods=["GET", "POST"])
@roles_required("admin")
def machines():
    db = _db()
    try:
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            name = request.form.get("name", "").strip()
            station_id_raw = request.form.get("station_id", "").strip()
            cmms_code = request.form.get("cmms_device_code", "").strip() or None

            if not code or not name or not station_id_raw:
                flash("کد، نام و ایستگاه ماشین الزامی است.", "error")
                return redirect(url_for("production.machines"))

            try:
                station_id = int(station_id_raw)
                station = db.execute(
                    "SELECT id FROM production_stations WHERE id = ? AND is_active = 1",
                    (station_id,),
                ).fetchone()
                if station is None:
                    raise ValueError("ایستگاه انتخاب‌شده معتبر نیست.")

                if cmms_code:
                    device = db.execute(
                        "SELECT cod, name FROM dastgahjadid WHERE cod = ?",
                        (cmms_code,),
                    ).fetchone()
                    if device is None:
                        raise ValueError("کد دستگاه CMMS پیدا نشد. ماشین تولید بدون اتصال CMMS ثبت نمی‌شود.")

                db.execute(
                    """INSERT INTO production_machines
                       (code,name,cmms_device_code,station_id,is_active)
                       VALUES (?,?,?,?,1)""",
                    (code, name, cmms_code, station_id),
                )
                db.commit()
                flash("ماشین تولید با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت ماشین انجام نشد: {exc}", "error")
            return redirect(url_for("production.machines"))

        rows = db.execute(
            """SELECT m.id, m.code, m.name, m.cmms_device_code, m.is_active,
                      s.code AS station_code, s.name AS station_name,
                      d.name AS cmms_device_name
               FROM production_machines m
               JOIN production_stations s ON s.id = m.station_id
               LEFT JOIN dastgahjadid d ON d.cod = m.cmms_device_code
               ORDER BY m.name"""
        ).fetchall()
        stations_rows = db.execute(
            "SELECT id, code, name FROM production_stations WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        devices = db.execute(
            "SELECT cod, name FROM dastgahjadid ORDER BY name"
        ).fetchall()
        return render_template(
            "production_machines.html",
            rows=rows,
            stations=stations_rows,
            devices=devices,
        )
    finally:
        db.close()


@production_bp.route("/employees", methods=["GET", "POST"])
@roles_required("admin")
def employees():
    db = _db()
    try:
        if request.method == "POST":
            personnel_code = request.form.get("personnel_code", "").strip()
            full_name = request.form.get("full_name", "").strip()
            user_id_raw = request.form.get("user_id", "").strip()

            if not personnel_code or not full_name:
                flash("کد پرسنلی و نام و نام خانوادگی الزامی است.", "error")
                return redirect(url_for("production.employees"))

            try:
                user_id = int(user_id_raw) if user_id_raw else None
                if user_id is not None:
                    user = db.execute(
                        "SELECT id FROM users WHERE id = ? AND is_active = 1",
                        (user_id,),
                    ).fetchone()
                    if user is None:
                        raise ValueError("کاربر انتخاب‌شده معتبر نیست.")

                db.execute(
                    """INSERT INTO production_employees
                       (personnel_code,full_name,is_active,user_id)
                       VALUES (?,?,1,?)""",
                    (personnel_code, full_name, user_id),
                )
                db.commit()
                flash("پرسنل تولید با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت پرسنل انجام نشد: {exc}", "error")
            return redirect(url_for("production.employees"))

        rows = db.execute(
            """SELECT e.id, e.personnel_code, e.full_name, e.is_active,
                      e.user_id, u.username
               FROM production_employees e
               LEFT JOIN users u ON u.id = e.user_id
               ORDER BY e.full_name"""
        ).fetchall()
        users = db.execute(
            "SELECT id, username, full_name FROM users WHERE is_active = 1 ORDER BY full_name, username"
        ).fetchall()
        return render_template("production_employees.html", rows=rows, users=users)
    finally:
        db.close()


@production_bp.route("/shifts", methods=["GET", "POST"])
@roles_required("admin")
def shifts():
    db = _db()
    try:
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            name = request.form.get("name", "").strip()
            start_time = request.form.get("start_time", "").strip()
            end_time = request.form.get("end_time", "").strip()
            crosses_midnight = 1 if request.form.get("crosses_midnight") == "1" else 0

            if not code or not name or not start_time or not end_time:
                flash("کد، نام، ساعت شروع و ساعت پایان شیفت الزامی است.", "error")
                return redirect(url_for("production.shifts"))

            try:
                # TIME از SQL Server مقدار HH:MM یا HH:MM:SS می‌پذیرد.
                db.execute(
                    """INSERT INTO production_shifts
                       (code,name,start_time,end_time,crosses_midnight,is_active)
                       VALUES (?,?,?,?,?,1)""",
                    (code, name, start_time, end_time, crosses_midnight),
                )
                db.commit()
                flash("شیفت با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت شیفت انجام نشد: {exc}", "error")
            return redirect(url_for("production.shifts"))

        rows = db.execute(
            """SELECT id, code, name, start_time, end_time, crosses_midnight, is_active
               FROM production_shifts ORDER BY code"""
        ).fetchall()
        return render_template("production_shifts.html", rows=rows)
    finally:
        db.close()
