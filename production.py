# -*- coding: utf-8 -*-
"""ماژول تولید — فاز اول: داشبورد و Master Data پایه."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import math
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


@production_bp.route("/station-products", methods=["GET", "POST"])
@roles_required("admin")
def station_products():
    db = _db()
    try:
        if request.method == "POST":
            station_id_raw = request.form.get("station_id", "").strip()
            product_id_raw = request.form.get("product_id", "").strip()
            cycle_raw = request.form.get("standard_cycle_time_seconds", "").strip()
            qty_raw = request.form.get("standard_qty_1h", "").strip()
            waste_raw = request.form.get("allowed_waste_percent", "").strip()

            if not station_id_raw or not product_id_raw:
                flash("ایستگاه و محصول الزامی است.", "error")
                return redirect(url_for("production.station_products"))

            try:
                station_id = int(station_id_raw)
                product_id = int(product_id_raw)
                station = db.execute(
                    "SELECT id FROM production_stations WHERE id = ? AND is_active = 1",
                    (station_id,),
                ).fetchone()
                product = db.execute(
                    "SELECT id FROM production_products WHERE id = ? AND is_active = 1",
                    (product_id,),
                ).fetchone()
                if station is None or product is None:
                    raise ValueError("ایستگاه یا محصول انتخاب‌شده معتبر نیست.")

                def _number(value, field_name, minimum=0):
                    if not value:
                        return None
                    number = float(value)
                    if number < minimum:
                        raise ValueError(f"{field_name} نمی‌تواند منفی باشد.")
                    return number

                cycle = _number(cycle_raw, "زمان سیکل")
                qty = _number(qty_raw, "استاندارد تولید ساعتی")
                waste = _number(waste_raw, "حد مجاز ضایعات")
                if waste is not None and waste > 100:
                    raise ValueError("حد مجاز ضایعات باید بین 0 تا 100 درصد باشد.")

                db.execute(
                    """INSERT INTO production_station_products
                       (station_id,product_id,standard_cycle_time_seconds,standard_qty_1h,allowed_waste_percent,is_active)
                       VALUES (?,?,?,?,?,1)""",
                    (station_id, product_id, cycle, qty, waste),
                )
                db.commit()
                flash("رابط محصول و ایستگاه با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت رابطه انجام نشد: {exc}", "error")
            return redirect(url_for("production.station_products"))

        rows = db.execute(
            """SELECT sp.id, sp.standard_cycle_time_seconds, sp.standard_qty_1h,
                      sp.allowed_waste_percent, sp.is_active,
                      s.code AS station_code, s.name AS station_name,
                      p.code AS product_code, p.name AS product_name
               FROM production_station_products sp
               JOIN production_stations s ON s.id = sp.station_id
               JOIN production_products p ON p.id = sp.product_id
               ORDER BY s.name, p.name"""
        ).fetchall()
        stations_rows = db.execute(
            "SELECT id, code, name FROM production_stations WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        products_rows = db.execute(
            "SELECT id, code, name FROM production_products WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        return render_template(
            "production_station_products.html",
            rows=rows,
            stations=stations_rows,
            products=products_rows,
        )
    finally:
        db.close()


@production_bp.route("/plans", methods=["GET", "POST"])
@roles_required("admin")
def plans():
    db = _db()
    try:
        if request.method == "POST":
            plan_date = request.form.get("plan_date", "").strip()
            notes = request.form.get("notes", "").strip() or None

            if not plan_date:
                flash("تاریخ برنامه الزامی است.", "error")
                return redirect(url_for("production.plans"))

            try:
                db.execute(
                    """INSERT INTO production_plans
                       (plan_date,status,created_by,notes)
                       VALUES (?, 'draft', ?, ?)""",
                    (plan_date, session.get("user_id"), notes),
                )
                db.commit()
                flash("برنامه تولید با موفقیت ایجاد شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ایجاد برنامه انجام نشد: {exc}", "error")
            return redirect(url_for("production.plans"))

        rows = db.execute(
            """SELECT p.id, p.plan_date, p.status, p.created_by, p.approved_by,
                      p.created_at, p.approved_at, p.notes,
                      u.full_name AS creator_name,
                      au.full_name AS approver_name,
                      COUNT(i.id) AS item_count
               FROM production_plans p
               LEFT JOIN users u ON u.id = p.created_by
               LEFT JOIN users au ON au.id = p.approved_by
               LEFT JOIN production_plan_items i ON i.plan_id = p.id
               GROUP BY p.id, p.plan_date, p.status, p.created_by, p.approved_by,
                        p.created_at, p.approved_at, p.notes,
                        u.full_name, au.full_name
               ORDER BY p.plan_date DESC, p.id DESC"""
        ).fetchall()
        return render_template("production_plans.html", rows=rows)
    finally:
        db.close()


@production_bp.route("/plans/<int:plan_id>", methods=["GET", "POST"])
@roles_required("admin")
def plan_detail(plan_id):
    db = _db()
    try:
        plan = db.execute(
            """SELECT p.id, p.plan_date, p.status, p.created_by, p.approved_by,
                      p.created_at, p.approved_at, p.notes,
                      u.full_name AS creator_name,
                      au.full_name AS approver_name
               FROM production_plans p
               LEFT JOIN users u ON u.id = p.created_by
               LEFT JOIN users au ON au.id = p.approved_by
               WHERE p.id = ?""",
            (plan_id,),
        ).fetchone()
        if plan is None:
            flash("برنامه پیدا نشد.", "error")
            return redirect(url_for("production.plans"))

        if request.method == "POST":
            if plan["status"] != "draft":
                flash("برنامه تأییدشده قابل تغییر نیست.", "error")
                return redirect(url_for("production.plan_detail", plan_id=plan_id))

            product_id_raw = request.form.get("product_id", "").strip()
            station_id_raw = request.form.get("station_id", "").strip()
            target_raw = request.form.get("target_qty", "").strip()
            management_target_raw = request.form.get("management_target_qty", "").strip()
            work_day = request.form.get("work_day", "").strip()
            notes = request.form.get("notes", "").strip() or None

            if not product_id_raw or not target_raw or not work_day:
                flash("محصول، مقدار هدف و روز کاری الزامی است.", "error")
                return redirect(url_for("production.plan_detail", plan_id=plan_id))

            try:
                product_id = int(product_id_raw)
                station_id = int(station_id_raw) if station_id_raw else None
                target_qty = float(target_raw)
                management_target_qty = (
                    float(management_target_raw) if management_target_raw else None
                )

                if not math.isfinite(target_qty) or target_qty <= 0:
                    raise ValueError("مقدار هدف باید یک عدد معتبر و بیشتر از صفر باشد.")
                if management_target_qty is not None and (not math.isfinite(management_target_qty) or management_target_qty < 0):
                    raise ValueError("هدف مدیریتی نمی‌تواند منفی باشد.")

                product = db.execute(
                    "SELECT id FROM production_products WHERE id = ? AND is_active = 1",
                    (product_id,),
                ).fetchone()
                if product is None:
                    raise ValueError("محصول انتخاب‌شده معتبر نیست.")

                if station_id is not None:
                    station = db.execute(
                        "SELECT id FROM production_stations WHERE id = ? AND is_active = 1",
                        (station_id,),
                    ).fetchone()
                    if station is None:
                        raise ValueError("ایستگاه انتخاب‌شده معتبر نیست.")

                    mapping = db.execute(
                        """SELECT id FROM production_station_products
                           WHERE station_id = ? AND product_id = ? AND is_active = 1""",
                        (station_id, product_id),
                    ).fetchone()
                    if mapping is None:
                        raise ValueError(
                            "برای این محصول و ایستگاه هنوز رابطه فعال در «استاندارد محصول/ایستگاه» ثبت نشده است."
                        )

                db.execute(
                    """INSERT INTO production_plan_items
                       (plan_id,product_id,station_id,target_qty,management_target_qty,work_day,notes)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        plan_id,
                        product_id,
                        station_id,
                        target_qty,
                        management_target_qty,
                        work_day,
                        notes,
                    ),
                )
                db.commit()
                flash("آیتم برنامه با موفقیت اضافه شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت آیتم انجام نشد: {exc}", "error")
            return redirect(url_for("production.plan_detail", plan_id=plan_id))

        items = db.execute(
            """SELECT i.id, i.product_id, i.station_id, i.target_qty,
                      i.management_target_qty, i.work_day, i.notes,
                      p.code AS product_code, p.name AS product_name,
                      s.code AS station_code, s.name AS station_name
               FROM production_plan_items i
               JOIN production_products p ON p.id = i.product_id
               LEFT JOIN production_stations s ON s.id = i.station_id
               WHERE i.plan_id = ?
               ORDER BY i.work_day, i.id""",
            (plan_id,),
        ).fetchall()
        products_rows = db.execute(
            "SELECT id, code, name FROM production_products WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        stations_rows = db.execute(
            "SELECT id, code, name FROM production_stations WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        return render_template(
            "production_plan_detail.html",
            plan=plan,
            items=items,
            products=products_rows,
            stations=stations_rows,
        )
    finally:
        db.close()


@production_bp.route("/plans/<int:plan_id>/approve", methods=["POST"])
@roles_required("admin")
def approve_plan(plan_id):
    db = _db()
    try:
        plan = db.execute(
            "SELECT id, status FROM production_plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
        if plan is None:
            flash("برنامه پیدا نشد.", "error")
            return redirect(url_for("production.plans"))

        if plan["status"] != "draft":
            flash("این برنامه قبلاً از حالت پیش‌نویس خارج شده است.", "error")
            return redirect(url_for("production.plan_detail", plan_id=plan_id))

        item_count = db.execute(
            "SELECT COUNT(*) AS n FROM production_plan_items WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()["n"]
        if item_count == 0:
            flash("برنامه بدون آیتم قابل تأیید نیست.", "error")
            return redirect(url_for("production.plan_detail", plan_id=plan_id))

        db.execute(
            """UPDATE production_plans
               SET status = 'approved', approved_by = ?, approved_at = SYSUTCDATETIME()
               WHERE id = ? AND status = 'draft'""",
            (session.get("user_id"), plan_id),
        )
        updated = db.execute(
            """UPDATE production_plans
               SET status = 'approved', approved_by = ?, approved_at = SYSUTCDATETIME()
               WHERE id = ? AND status = 'draft'""",
            (session.get("user_id"), plan_id),
        )
        if updated.rowcount != 1:
            db.rollback()
            flash("برنامه همزمان توسط کاربر دیگری تغییر کرده است؛ دوباره بررسی کنید.", "error")
            return redirect(url_for("production.plan_detail", plan_id=plan_id))
        db.commit()
        flash("برنامه با موفقیت تأیید شد و قفل گردید.", "success")
        return redirect(url_for("production.plan_detail", plan_id=plan_id))
    except Exception as exc:
        db.rollback()
        flash(f"تأیید برنامه انجام نشد: {exc}", "error")
        return redirect(url_for("production.plan_detail", plan_id=plan_id))
    finally:
        db.close()

@production_bp.route("/plans/<int:plan_id>/items/<int:item_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_plan_item(plan_id, item_id):
    db = _db()
    try:
        plan = db.execute("SELECT id, status FROM production_plans WHERE id = ?", (plan_id,)).fetchone()
        if plan is None:
            flash("برنامه پیدا نشد.", "error")
            return redirect(url_for("production.plans"))
        if plan["status"] != "draft":
            flash("آیتم‌های برنامه تأییدشده قابل حذف نیستند.", "error")
            return redirect(url_for("production.plan_detail", plan_id=plan_id))
        result = db.execute("DELETE FROM production_plan_items WHERE id = ? AND plan_id = ?", (item_id, plan_id))
        if result.rowcount != 1:
            db.rollback()
            flash("آیتم موردنظر پیدا نشد.", "error")
        else:
            db.commit()
            flash("آیتم برنامه حذف شد.", "success")
        return redirect(url_for("production.plan_detail", plan_id=plan_id))
    except Exception as exc:
        db.rollback()
        flash(f"حذف آیتم انجام نشد: {exc}", "error")
        return redirect(url_for("production.plan_detail", plan_id=plan_id))
    finally:
        db.close()
