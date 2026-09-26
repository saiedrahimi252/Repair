# -*- coding: utf-8 -*-
"""ماژول تولید — فاز اول: داشبورد و Master Data پایه."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import math
from database import get_connection
from auth import roles_required

production_bp = Blueprint("production", __name__, url_prefix="/production")


def _db():
    return get_connection(session.get("company_db") or "repair")





def _ensure_work_calendar_table(db):
    """تقویم کاری تولید: زمان برنامه‌ریزی‌شده را مستقل از حضور و توقف نگه می‌دارد."""
    db.execute("""
        IF OBJECT_ID('dbo.production_work_calendar', 'U') IS NULL
        BEGIN
            CREATE TABLE production_work_calendar (
                id INT IDENTITY(1,1) PRIMARY KEY,
                work_date DATE NOT NULL,
                shift_id INT NOT NULL,
                station_id INT NOT NULL,
                is_working BIT NOT NULL DEFAULT 1,
                planned_minutes FLOAT NOT NULL DEFAULT 0,
                notes NVARCHAR(MAX) NULL,
                created_by INT NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                CONSTRAINT CK_prod_calendar_minutes CHECK (planned_minutes >= 0 AND planned_minutes <= 1440),
                CONSTRAINT UQ_prod_calendar_date_shift_station UNIQUE (work_date, shift_id, station_id),
                CONSTRAINT FK_prod_calendar_shift FOREIGN KEY (shift_id) REFERENCES production_shifts(id),
                CONSTRAINT FK_prod_calendar_station FOREIGN KEY (station_id) REFERENCES production_stations(id)
            )
        END
    """)
    db.commit()


def _shift_minutes(start_time, end_time, crosses_midnight):
    from datetime import datetime, date, timedelta
    start = datetime.combine(date.today(), start_time)
    end = datetime.combine(date.today(), end_time)
    if crosses_midnight and end <= start:
        end += timedelta(days=1)
    elif end < start:
        end += timedelta(days=1)
    return max(0.0, (end - start).total_seconds() / 60.0)


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


@production_bp.route("/stop-types", methods=["GET", "POST"])
@roles_required("admin")
def stop_types():
    db = _db()
    try:
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip() or None
            counts = 1 if request.form.get("counts_as_unavailability") == "1" else 0
            if not code or not name:
                flash("کد و نام نوع توقف الزامی است.", "error")
                return redirect(url_for("production.stop_types"))
            try:
                db.execute("INSERT INTO production_stop_types (code,name,category,counts_as_unavailability,is_active) VALUES (?,?,?,?,1)", (code,name,category,counts))
                db.commit()
                flash("نوع توقف با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت نوع توقف انجام نشد: {exc}", "error")
            return redirect(url_for("production.stop_types"))
        rows = db.execute("SELECT id,code,name,category,counts_as_unavailability,is_active FROM production_stop_types ORDER BY code").fetchall()
        return render_template("production_stop_types.html", rows=rows)
    finally:
        db.close()



@production_bp.route("/stops", methods=["GET", "POST"])
@roles_required("admin")
def production_stops():
    db = _db()
    try:
        if request.method == "POST":
            plan_item_id_raw = request.form.get("plan_item_id", "").strip()
            shift_id_raw = request.form.get("shift_id", "").strip()
            stop_type_id_raw = request.form.get("stop_type_id", "").strip()
            employee_id_raw = request.form.get("employee_id", "").strip()
            machine_id_raw = request.form.get("machine_id", "").strip()
            production_date = request.form.get("production_date", "").strip()
            start_at_raw = request.form.get("start_at", "").strip()
            end_at_raw = request.form.get("end_at", "").strip()
            notes = request.form.get("notes", "").strip() or None

            if not shift_id_raw or not stop_type_id_raw or not production_date or not start_at_raw or not end_at_raw:
                flash("شیفت، نوع توقف، تاریخ، زمان شروع و زمان پایان الزامی است.", "error")
                return redirect(url_for("production.production_stops"))

            try:
                from datetime import datetime

                plan_item_id = int(plan_item_id_raw) if plan_item_id_raw else None
                shift_id = int(shift_id_raw)
                stop_type_id = int(stop_type_id_raw)
                employee_id = int(employee_id_raw) if employee_id_raw else None
                machine_id = int(machine_id_raw) if machine_id_raw else None

                start_at = datetime.fromisoformat(start_at_raw)
                end_at = datetime.fromisoformat(end_at_raw)
                if end_at <= start_at:
                    raise ValueError("زمان پایان توقف باید بعد از زمان شروع باشد.")

                duration_minutes = (end_at - start_at).total_seconds() / 60.0
                if not math.isfinite(duration_minutes) or duration_minutes <= 0:
                    raise ValueError("مدت توقف معتبر نیست.")

                shift = db.execute(
                    "SELECT id FROM production_shifts WHERE id = ? AND is_active = 1",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise ValueError("شیفت انتخاب‌شده معتبر نیست.")

                stop_type = db.execute(
                    "SELECT id FROM production_stop_types WHERE id = ? AND is_active = 1",
                    (stop_type_id,),
                ).fetchone()
                if stop_type is None:
                    raise ValueError("نوع توقف انتخاب‌شده معتبر نیست.")

                if plan_item_id is not None:
                    item = db.execute(
                        """SELECT i.id, i.station_id, p.status AS plan_status
                           FROM production_plan_items i
                           JOIN production_plans p ON p.id = i.plan_id
                           WHERE i.id = ?""",
                        (plan_item_id,),
                    ).fetchone()
                    if item is None:
                        raise ValueError("آیتم برنامه پیدا نشد.")
                    if item["plan_status"] != "approved":
                        raise ValueError("ثبت توقف برای آیتم برنامه فقط پس از تأیید برنامه مجاز است.")
                else:
                    item = None

                if employee_id is not None:
                    employee = db.execute(
                        "SELECT id FROM production_employees WHERE id = ? AND is_active = 1",
                        (employee_id,),
                    ).fetchone()
                    if employee is None:
                        raise ValueError("پرسنل انتخاب‌شده معتبر نیست.")

                if machine_id is not None:
                    machine = db.execute(
                        "SELECT id, station_id FROM production_machines WHERE id = ? AND is_active = 1",
                        (machine_id,),
                    ).fetchone()
                    if machine is None:
                        raise ValueError("ماشین انتخاب‌شده معتبر نیست.")
                    if item is not None and item["station_id"] is not None and machine["station_id"] != item["station_id"]:
                        raise ValueError("ماشین انتخاب‌شده متعلق به ایستگاه این آیتم برنامه نیست.")

                db.execute(
                    """INSERT INTO production_stops
                       (plan_item_id,production_date,shift_id,employee_id,machine_id,stop_type_id,
                        start_at,end_at,duration_minutes,notes,created_by)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (plan_item_id, production_date, shift_id, employee_id, machine_id, stop_type_id,
                     start_at, end_at, duration_minutes, notes, session.get("user_id")),
                )
                db.commit()
                flash("توقف با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت توقف انجام نشد: {exc}", "error")
            return redirect(url_for("production.production_stops"))

        rows = db.execute(
            """SELECT st.id, st.production_date, st.start_at, st.end_at,
                      st.duration_minutes, st.notes,
                      p.code AS product_code, p.name AS product_name,
                      s.name AS station_name,
                      sh.name AS shift_name,
                      pe.full_name AS employee_name,
                      m.name AS machine_name,
                      pt.code AS stop_type_code, pt.name AS stop_type_name,
                      pt.category AS stop_category
               FROM production_stops st
               LEFT JOIN production_plan_items i ON i.id = st.plan_item_id
               LEFT JOIN production_products p ON p.id = i.product_id
               LEFT JOIN production_stations s ON s.id = i.station_id
               JOIN production_shifts sh ON sh.id = st.shift_id
               LEFT JOIN production_employees pe ON pe.id = st.employee_id
               LEFT JOIN production_machines m ON m.id = st.machine_id
               JOIN production_stop_types pt ON pt.id = st.stop_type_id
               ORDER BY st.production_date DESC, st.start_at DESC, st.id DESC"""
        ).fetchall()

        plan_items = db.execute(
            """SELECT i.id, i.work_day, p.plan_date,
                      pr.code AS product_code, pr.name AS product_name,
                      s.name AS station_name
               FROM production_plan_items i
               JOIN production_plans p ON p.id = i.plan_id
               JOIN production_products pr ON pr.id = i.product_id
               LEFT JOIN production_stations s ON s.id = i.station_id
               WHERE p.status = 'approved'
               ORDER BY i.work_day DESC, i.id DESC"""
        ).fetchall()
        shifts_rows = db.execute(
            "SELECT id, code, name FROM production_shifts WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        employees_rows = db.execute(
            "SELECT id, personnel_code, full_name FROM production_employees WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()
        machines_rows = db.execute(
            "SELECT id, code, name, station_id FROM production_machines WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        stop_types_rows = db.execute(
            "SELECT id, code, name, category FROM production_stop_types WHERE is_active = 1 ORDER BY code"
        ).fetchall()

        return render_template(
            "production_stops.html",
            rows=rows,
            plan_items=plan_items,
            shifts=shifts_rows,
            employees=employees_rows,
            machines=machines_rows,
            stop_types=stop_types_rows,
        )
    finally:
        db.close()




@production_bp.route("/defect-types", methods=["GET", "POST"])
@roles_required("admin")
def defect_types():
    db = _db()
    try:
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None
            if not code or not name:
                flash("کد و نام نوع عیب الزامی است.", "error")
                return redirect(url_for("production.defect_types"))
            try:
                db.execute(
                    "INSERT INTO production_defect_types (code,name,description,is_active) VALUES (?,?,?,1)",
                    (code, name, description),
                )
                db.commit()
                flash("نوع عیب با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت نوع عیب انجام نشد: {exc}", "error")
            return redirect(url_for("production.defect_types"))

        rows = db.execute(
            "SELECT id,code,name,description,is_active FROM production_defect_types ORDER BY code"
        ).fetchall()
        return render_template("production_defect_types.html", rows=rows)
    finally:
        db.close()


@production_bp.route("/waste", methods=["GET", "POST"])
@roles_required("admin")
def production_waste_entries():
    db = _db()
    try:
        if request.method == "POST":
            plan_item_id_raw = request.form.get("plan_item_id", "").strip()
            shift_id_raw = request.form.get("shift_id", "").strip()
            defect_type_id_raw = request.form.get("defect_type_id", "").strip()
            employee_id_raw = request.form.get("employee_id", "").strip()
            machine_id_raw = request.form.get("machine_id", "").strip()
            production_date = request.form.get("production_date", "").strip()
            record_type = request.form.get("record_type", "").strip().lower()
            classification = request.form.get("classification", "").strip() or None
            quantity_raw = request.form.get("quantity", "").strip()
            notes = request.form.get("notes", "").strip() or None

            if not shift_id_raw or not production_date or not record_type or not quantity_raw:
                flash("شیفت، تاریخ، نوع رکورد و مقدار الزامی است.", "error")
                return redirect(url_for("production.production_waste_entries"))

            try:
                plan_item_id = int(plan_item_id_raw) if plan_item_id_raw else None
                shift_id = int(shift_id_raw)
                defect_type_id = int(defect_type_id_raw) if defect_type_id_raw else None
                employee_id = int(employee_id_raw) if employee_id_raw else None
                machine_id = int(machine_id_raw) if machine_id_raw else None
                quantity = float(quantity_raw)

                if record_type not in ("waste", "rework"):
                    raise ValueError("نوع رکورد باید ضایعات یا دوباره‌کاری باشد.")
                if not math.isfinite(quantity) or quantity <= 0:
                    raise ValueError("مقدار باید عدد معتبر و بیشتر از صفر باشد.")

                shift = db.execute(
                    "SELECT id FROM production_shifts WHERE id = ? AND is_active = 1",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise ValueError("شیفت انتخاب‌شده معتبر نیست.")

                item = None
                if plan_item_id is not None:
                    item = db.execute(
                        """SELECT i.id, i.station_id, p.status AS plan_status
                           FROM production_plan_items i
                           JOIN production_plans p ON p.id = i.plan_id
                           WHERE i.id = ?""",
                        (plan_item_id,),
                    ).fetchone()
                    if item is None:
                        raise ValueError("آیتم برنامه پیدا نشد.")
                    if item["plan_status"] != "approved":
                        raise ValueError("ثبت ضایعات/دوباره‌کاری فقط برای برنامه تأییدشده مجاز است.")

                if defect_type_id is not None:
                    defect = db.execute(
                        "SELECT id FROM production_defect_types WHERE id = ? AND is_active = 1",
                        (defect_type_id,),
                    ).fetchone()
                    if defect is None:
                        raise ValueError("نوع عیب انتخاب‌شده معتبر نیست.")

                if employee_id is not None:
                    employee = db.execute(
                        "SELECT id FROM production_employees WHERE id = ? AND is_active = 1",
                        (employee_id,),
                    ).fetchone()
                    if employee is None:
                        raise ValueError("پرسنل انتخاب‌شده معتبر نیست.")

                if machine_id is not None:
                    machine = db.execute(
                        "SELECT id, station_id FROM production_machines WHERE id = ? AND is_active = 1",
                        (machine_id,),
                    ).fetchone()
                    if machine is None:
                        raise ValueError("ماشین انتخاب‌شده معتبر نیست.")
                    if item is not None and item["station_id"] is not None and machine["station_id"] != item["station_id"]:
                        raise ValueError("ماشین انتخاب‌شده متعلق به ایستگاه آیتم برنامه نیست.")

                db.execute(
                    """INSERT INTO production_waste_entries
                       (plan_item_id,production_date,shift_id,employee_id,machine_id,
                        defect_type_id,record_type,classification,quantity,notes,created_by)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (plan_item_id, production_date, shift_id, employee_id, machine_id,
                     defect_type_id, record_type, classification, quantity, notes,
                     session.get("user_id")),
                )
                db.commit()
                flash("رکورد ضایعات/دوباره‌کاری با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت رکورد انجام نشد: {exc}", "error")
            return redirect(url_for("production.production_waste_entries"))

        rows = db.execute(
            """SELECT w.id, w.production_date, w.record_type, w.classification,
                      w.quantity, w.notes,
                      pr.code AS product_code, pr.name AS product_name,
                      s.name AS station_name, sh.name AS shift_name,
                      e.full_name AS employee_name, m.name AS machine_name,
                      d.code AS defect_code, d.name AS defect_name
               FROM production_waste_entries w
               LEFT JOIN production_plan_items i ON i.id = w.plan_item_id
               LEFT JOIN production_products pr ON pr.id = i.product_id
               LEFT JOIN production_stations s ON s.id = i.station_id
               JOIN production_shifts sh ON sh.id = w.shift_id
               LEFT JOIN production_employees e ON e.id = w.employee_id
               LEFT JOIN production_machines m ON m.id = w.machine_id
               LEFT JOIN production_defect_types d ON d.id = w.defect_type_id
               ORDER BY w.production_date DESC, w.id DESC"""
        ).fetchall()

        plan_items = db.execute(
            """SELECT i.id, i.work_day, pr.code AS product_code,
                      pr.name AS product_name, s.name AS station_name
               FROM production_plan_items i
               JOIN production_plans p ON p.id = i.plan_id
               JOIN production_products pr ON pr.id = i.product_id
               LEFT JOIN production_stations s ON s.id = i.station_id
               WHERE p.status = 'approved'
               ORDER BY i.work_day DESC, i.id DESC"""
        ).fetchall()
        shifts_rows = db.execute(
            "SELECT id, code, name FROM production_shifts WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        employees_rows = db.execute(
            "SELECT id, personnel_code, full_name FROM production_employees WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()
        machines_rows = db.execute(
            "SELECT id, code, name, station_id FROM production_machines WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        defects_rows = db.execute(
            "SELECT id, code, name FROM production_defect_types WHERE is_active = 1 ORDER BY code"
        ).fetchall()

        return render_template(
            "production_waste.html",
            rows=rows,
            plan_items=plan_items,
            shifts=shifts_rows,
            employees=employees_rows,
            machines=machines_rows,
            defects=defects_rows,
        )
    finally:
        db.close()


@production_bp.route("/entries", methods=["GET", "POST"])
@roles_required("admin")
def production_entries():
    db = _db()
    try:
        if request.method == "POST":
            plan_item_id_raw = request.form.get("plan_item_id", "").strip()
            shift_id_raw = request.form.get("shift_id", "").strip()
            employee_id_raw = request.form.get("employee_id", "").strip()
            machine_id_raw = request.form.get("machine_id", "").strip()
            production_date = request.form.get("production_date", "").strip()
            quantity_raw = request.form.get("quantity", "").strip()
            notes = request.form.get("notes", "").strip() or None

            if not plan_item_id_raw or not shift_id_raw or not employee_id_raw or not production_date or not quantity_raw:
                flash("برنامه، شیفت، پرسنل، تاریخ تولید و مقدار تولید الزامی است.", "error")
                return redirect(url_for("production.production_entries"))

            try:
                plan_item_id = int(plan_item_id_raw)
                shift_id = int(shift_id_raw)
                employee_id = int(employee_id_raw)
                machine_id = int(machine_id_raw) if machine_id_raw else None
                quantity = float(quantity_raw)

                if not math.isfinite(quantity) or quantity <= 0:
                    raise ValueError("مقدار تولید باید عدد معتبر و بیشتر از صفر باشد.")

                item = db.execute(
                    """SELECT i.id, i.product_id, i.station_id, i.work_day,
                              p.status AS plan_status,
                              pr.name AS product_name,
                              s.name AS station_name
                       FROM production_plan_items i
                       JOIN production_plans p ON p.id = i.plan_id
                       JOIN production_products pr ON pr.id = i.product_id
                       LEFT JOIN production_stations s ON s.id = i.station_id
                       WHERE i.id = ?""",
                    (plan_item_id,),
                ).fetchone()
                if item is None:
                    raise ValueError("آیتم برنامه پیدا نشد.")
                if item["plan_status"] != "approved":
                    raise ValueError("ثبت تولید فقط برای برنامه تأییدشده مجاز است.")

                shift = db.execute(
                    "SELECT id FROM production_shifts WHERE id = ? AND is_active = 1",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise ValueError("شیفت انتخاب‌شده معتبر نیست.")

                employee = db.execute(
                    "SELECT id FROM production_employees WHERE id = ? AND is_active = 1",
                    (employee_id,),
                ).fetchone()
                if employee is None:
                    raise ValueError("پرسنل انتخاب‌شده معتبر نیست.")

                if machine_id is not None:
                    machine = db.execute(
                        "SELECT id, station_id FROM production_machines WHERE id = ? AND is_active = 1",
                        (machine_id,),
                    ).fetchone()
                    if machine is None:
                        raise ValueError("ماشین انتخاب‌شده معتبر نیست.")
                    if item["station_id"] is not None and machine["station_id"] != item["station_id"]:
                        raise ValueError("ماشین انتخاب‌شده متعلق به ایستگاه این آیتم برنامه نیست.")

                db.execute(
                    """INSERT INTO production_entries
                       (plan_item_id,production_date,shift_id,employee_id,machine_id,quantity,notes,created_by)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (plan_item_id, production_date, shift_id, employee_id, machine_id,
                     quantity, notes, session.get("user_id")),
                )
                db.commit()
                flash("تولید واقعی با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت تولید انجام نشد: {exc}", "error")
            return redirect(url_for("production.production_entries"))

        rows = db.execute(
            """SELECT e.id, e.production_date, e.quantity, e.notes, e.created_at,
                      pr.code AS product_code, pr.name AS product_name,
                      s.name AS station_name,
                      sh.name AS shift_name,
                      pe.full_name AS employee_name,
                      m.name AS machine_name
               FROM production_entries e
               JOIN production_plan_items i ON i.id = e.plan_item_id
               JOIN production_products pr ON pr.id = i.product_id
               LEFT JOIN production_stations s ON s.id = i.station_id
               JOIN production_shifts sh ON sh.id = e.shift_id
               JOIN production_employees pe ON pe.id = e.employee_id
               LEFT JOIN production_machines m ON m.id = e.machine_id
               ORDER BY e.production_date DESC, e.id DESC"""
        ).fetchall()

        plan_items = db.execute(
            """SELECT i.id, i.work_day, i.target_qty, p.plan_date,
                      pr.code AS product_code, pr.name AS product_name,
                      s.name AS station_name
               FROM production_plan_items i
               JOIN production_plans p ON p.id = i.plan_id
               JOIN production_products pr ON pr.id = i.product_id
               LEFT JOIN production_stations s ON s.id = i.station_id
               WHERE p.status = 'approved'
               ORDER BY i.work_day DESC, i.id DESC"""
        ).fetchall()
        shifts_rows = db.execute(
            "SELECT id, code, name FROM production_shifts WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        employees_rows = db.execute(
            "SELECT id, personnel_code, full_name FROM production_employees WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()
        machines_rows = db.execute(
            "SELECT id, code, name, station_id FROM production_machines WHERE is_active = 1 ORDER BY name"
        ).fetchall()

        return render_template(
            "production_entries.html",
            rows=rows,
            plan_items=plan_items,
            shifts=shifts_rows,
            employees=employees_rows,
            machines=machines_rows,
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


@production_bp.route("/employee-break-types", methods=["GET", "POST"])
@roles_required("admin")
def employee_break_types():
    db = _db()
    try:
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip().lower()
            counts = 1 if request.form.get("counts_as_unavailability") == "1" else 0
            if not code or not name or category not in {"break", "personal", "leave", "other"}:
                flash("کد، نام و دسته‌بندی معتبر الزامی است.", "error")
                return redirect(url_for("production.employee_break_types"))
            try:
                db.execute(
                    """INSERT INTO production_employee_break_types
                       (code,name,category,counts_as_unavailability)
                       VALUES (?,?,?,?)""",
                    (code, name, category, counts),
                )
                db.commit()
                flash("نوع وقفه پرسنلی ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت نوع وقفه انجام نشد: {exc}", "error")
            return redirect(url_for("production.employee_break_types"))

        rows = db.execute(
            """SELECT id, code, name, category, counts_as_unavailability, is_active
               FROM production_employee_break_types ORDER BY code"""
        ).fetchall()
        return render_template("production_employee_break_types.html", rows=rows)
    finally:
        db.close()


@production_bp.route("/employee-breaks", methods=["GET", "POST"])
@roles_required("admin")
def employee_breaks():
    db = _db()
    try:
        if request.method == "POST":
            attendance_id = int(request.form.get("attendance_id", "0"))
            break_type_id = int(request.form.get("break_type_id", "0"))
            start_at = request.form.get("start_at", "").strip()
            end_at = request.form.get("end_at", "").strip()
            notes = request.form.get("notes", "").strip() or None
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(start_at)
                end_dt = datetime.fromisoformat(end_at)
                if end_dt <= start_dt:
                    raise ValueError("زمان پایان باید بعد از شروع باشد.")
                attendance = db.execute(
                    """SELECT id, start_at, end_at
                       FROM production_attendance WHERE id = ?""",
                    (attendance_id,),
                ).fetchone()
                if attendance is None:
                    raise ValueError("رکورد حضور معتبر نیست.")
                break_type = db.execute(
                    """SELECT id FROM production_employee_break_types
                       WHERE id = ? AND is_active = 1""",
                    (break_type_id,),
                ).fetchone()
                if break_type is None:
                    raise ValueError("نوع وقفه معتبر نیست.")
                if attendance.start_at and start_dt < attendance.start_at:
                    raise ValueError("شروع وقفه قبل از شروع حضور است.")
                if attendance.end_at and end_dt > attendance.end_at:
                    raise ValueError("پایان وقفه بعد از پایان حضور است.")
                duration = (end_dt - start_dt).total_seconds() / 60.0
                db.execute(
                    """INSERT INTO production_employee_breaks
                       (attendance_id,break_type_id,start_at,end_at,duration_minutes,notes,created_by)
                       VALUES (?,?,?,?,?,?,?)""",
                    (attendance_id, break_type_id, start_at, end_at, duration, notes, session.get("user_id")),
                )
                db.commit()
                flash("وقفه پرسنلی ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت وقفه انجام نشد: {exc}", "error")
            return redirect(url_for("production.employee_breaks"))

        rows = db.execute(
            """SELECT b.id, b.start_at, b.end_at, b.duration_minutes, b.notes,
                      a.attendance_date, e.full_name AS employee_name,
                      sh.code AS shift_code, t.code AS type_code, t.name AS type_name
               FROM production_employee_breaks b
               JOIN production_attendance a ON a.id = b.attendance_id
               JOIN production_employees e ON e.id = a.employee_id
               JOIN production_shifts sh ON sh.id = a.shift_id
               JOIN production_employee_break_types t ON t.id = b.break_type_id
               ORDER BY b.start_at DESC, b.id DESC"""
        ).fetchall()
        attendance_rows = db.execute(
            """SELECT a.id, a.attendance_date, e.full_name AS employee_name,
                      sh.code AS shift_code
               FROM production_attendance a
               JOIN production_employees e ON e.id = a.employee_id
               JOIN production_shifts sh ON sh.id = a.shift_id
               ORDER BY a.attendance_date DESC, e.full_name"""
        ).fetchall()
        type_rows = db.execute(
            """SELECT id, code, name FROM production_employee_break_types
               WHERE is_active = 1 ORDER BY code"""
        ).fetchall()
        return render_template(
            "production_employee_breaks.html",
            rows=rows,
            attendance_rows=attendance_rows,
            type_rows=type_rows,
        )
    finally:
        db.close()


@production_bp.route("/attendance", methods=["GET", "POST"])
@roles_required("admin")
def attendance():
    """ثبت و مشاهده حضور و وضعیت نیروی تولید؛ بدون محاسبه زمان مفید/OEE."""
    db = _db()
    try:
        if request.method == "POST":
            attendance_date = request.form.get("attendance_date", "").strip()
            shift_id_raw = request.form.get("shift_id", "").strip()
            employee_id_raw = request.form.get("employee_id", "").strip()
            status = request.form.get("status", "").strip().lower()
            start_at = request.form.get("start_at", "").strip() or None
            end_at = request.form.get("end_at", "").strip() or None
            notes = request.form.get("notes", "").strip() or None

            allowed_statuses = {"present", "absent", "leave", "off"}
            if not attendance_date or not shift_id_raw or not employee_id_raw or status not in allowed_statuses:
                flash("تاریخ، شیفت، پرسنل و وضعیت حضور الزامی است.", "error")
                return redirect(url_for("production.attendance"))

            try:
                shift_id = int(shift_id_raw)
                employee_id = int(employee_id_raw)

                shift = db.execute(
                    "SELECT id FROM production_shifts WHERE id = ? AND is_active = 1",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise ValueError("شیفت انتخاب‌شده معتبر نیست.")

                employee = db.execute(
                    "SELECT id FROM production_employees WHERE id = ? AND is_active = 1",
                    (employee_id,),
                ).fetchone()
                if employee is None:
                    raise ValueError("پرسنل انتخاب‌شده معتبر نیست.")

                if start_at and end_at:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(start_at)
                    end_dt = datetime.fromisoformat(end_at)
                    if end_dt < start_dt:
                        raise ValueError("زمان پایان نمی‌تواند قبل از زمان شروع باشد.")

                db.execute(
                    """INSERT INTO production_attendance
                       (attendance_date,shift_id,employee_id,status,start_at,end_at,notes,created_by)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        attendance_date,
                        shift_id,
                        employee_id,
                        status,
                        start_at,
                        end_at,
                        notes,
                        session.get("user_id"),
                    ),
                )
                db.commit()
                flash("رکورد حضور تولید با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت حضور انجام نشد: {exc}", "error")
            return redirect(url_for("production.attendance"))

        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        shift_id_raw = request.args.get("shift_id", "").strip()
        employee_id_raw = request.args.get("employee_id", "").strip()

        filters = []
        params = []
        if date_from:
            filters.append("a.attendance_date >= ?")
            params.append(date_from)
        if date_to:
            filters.append("a.attendance_date <= ?")
            params.append(date_to)
        if shift_id_raw:
            try:
                shift_filter = int(shift_id_raw)
                filters.append("a.shift_id = ?")
                params.append(shift_filter)
            except ValueError:
                flash("شیفت فیلترشده معتبر نیست.", "error")
                return redirect(url_for("production.attendance"))
        if employee_id_raw:
            try:
                employee_filter = int(employee_id_raw)
                filters.append("a.employee_id = ?")
                params.append(employee_filter)
            except ValueError:
                flash("پرسنل فیلترشده معتبر نیست.", "error")
                return redirect(url_for("production.attendance"))

        where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""

        rows = db.execute(
            f"""SELECT a.id, a.attendance_date, a.status, a.start_at, a.end_at,
                       a.notes, a.created_at,
                       sh.code AS shift_code, sh.name AS shift_name,
                       e.personnel_code, e.full_name AS employee_name
                FROM production_attendance a
                JOIN production_shifts sh ON sh.id = a.shift_id
                JOIN production_employees e ON e.id = a.employee_id
                {where_sql}
                ORDER BY a.attendance_date DESC, sh.code, e.full_name, a.id DESC""",
            params,
        ).fetchall()

        shifts_rows = db.execute(
            "SELECT id, code, name FROM production_shifts WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        employees_rows = db.execute(
            "SELECT id, personnel_code, full_name FROM production_employees WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()

        return render_template(
            "production_attendance.html",
            rows=rows,
            shifts=shifts_rows,
            employees=employees_rows,
            filters={
                "date_from": date_from,
                "date_to": date_to,
                "shift_id": shift_id_raw,
                "employee_id": employee_id_raw,
            },
        )
    finally:
        db.close()


@production_bp.route("/control")
@roles_required("admin")
def production_control():
    """کنترل تجمیعی برنامه، تولید، ضایعات و دوباره‌کاری؛ بدون محاسبه OEE."""
    db = _db()
    try:
        from datetime import date

        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        product_id_raw = request.args.get("product_id", "").strip()
        station_id_raw = request.args.get("station_id", "").strip()
        shift_id_raw = request.args.get("shift_id", "").strip()
        employee_id_raw = request.args.get("employee_id", "").strip()

        # بازه پیش‌فرض: امروز تا امروز؛ کاربر می‌تواند آن را خالی کند تا همه تاریخ‌ها بررسی شوند.
        if not date_from and not date_to:
            today = date.today().isoformat()
            date_from = today
            date_to = today
        elif date_from and not date_to:
            date_to = date_from
        elif date_to and not date_from:
            date_from = date_to

        def _optional_int(raw, label):
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                raise ValueError(f"{label} نامعتبر است.")

        try:
            product_id = _optional_int(product_id_raw, "محصول")
            station_id = _optional_int(station_id_raw, "ایستگاه")
            shift_id = _optional_int(shift_id_raw, "شیفت")
            employee_id = _optional_int(employee_id_raw, "پرسنل")
            if date_from and date_to and date_from > date_to:
                raise ValueError("تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد.")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("production.production_control"))

        # فقط آیتم‌های برنامه تأییدشده در کنترل مبنا قرار می‌گیرند.
        item_filters = ["p.status = 'approved'"]
        item_params = []

        if date_from:
            item_filters.append("i.work_day >= ?")
            item_params.append(date_from)
        if date_to:
            item_filters.append("i.work_day <= ?")
            item_params.append(date_to)
        if product_id is not None:
            item_filters.append("i.product_id = ?")
            item_params.append(product_id)
        if station_id is not None:
            item_filters.append("i.station_id = ?")
            item_params.append(station_id)

        where_items = " AND ".join(item_filters)

        # فیلترهای رویداد تولید؛ تاریخ رویداد از work_day مستقل نگه داشته می‌شود.
        production_filters = []
        production_params = []
        if date_from:
            production_filters.append("e.production_date >= ?")
            production_params.append(date_from)
        if date_to:
            production_filters.append("e.production_date <= ?")
            production_params.append(date_to)
        if shift_id is not None:
            production_filters.append("e.shift_id = ?")
            production_params.append(shift_id)
        if employee_id is not None:
            production_filters.append("e.employee_id = ?")
            production_params.append(employee_id)

        production_where = (" AND " + " AND ".join(production_filters)) if production_filters else ""

        waste_filters = []
        waste_params = []
        if date_from:
            waste_filters.append("w.production_date >= ?")
            waste_params.append(date_from)
        if date_to:
            waste_filters.append("w.production_date <= ?")
            waste_params.append(date_to)
        if shift_id is not None:
            waste_filters.append("w.shift_id = ?")
            waste_params.append(shift_id)
        if employee_id is not None:
            waste_filters.append("w.employee_id = ?")
            waste_params.append(employee_id)

        waste_where = (" AND " + " AND ".join(waste_filters)) if waste_filters else ""

        stop_filters = []
        stop_params = []
        if date_from:
            stop_filters.append("st.production_date >= ?")
            stop_params.append(date_from)
        if date_to:
            stop_filters.append("st.production_date <= ?")
            stop_params.append(date_to)
        if shift_id is not None:
            stop_filters.append("st.shift_id = ?")
            stop_params.append(shift_id)
        if employee_id is not None:
            stop_filters.append("st.employee_id = ?")
            stop_params.append(employee_id)
        stop_where = (" AND " + " AND ".join(stop_filters)) if stop_filters else ""

        rows = db.execute(
            f"""SELECT
                    i.id AS plan_item_id,
                    i.work_day,
                    i.target_qty,
                    i.management_target_qty,
                    pr.code AS product_code,
                    pr.name AS product_name,
                    s.code AS station_code,
                    s.name AS station_name,
                    sp.allowed_waste_percent,
                    COALESCE((
                        SELECT SUM(e.quantity)
                        FROM production_entries e
                        WHERE e.plan_item_id = i.id
                        {production_where}
                    ), 0) AS actual_production,
                    COALESCE((
                        SELECT SUM(w.quantity)
                        FROM production_waste_entries w
                        WHERE w.plan_item_id = i.id
                          AND w.record_type = 'waste'
                        {waste_where}
                    ), 0) AS waste_qty,
                    COALESCE((
                        SELECT SUM(w.quantity)
                        FROM production_waste_entries w
                        WHERE w.plan_item_id = i.id
                          AND w.record_type = 'rework'
                        {waste_where}
                    ), 0) AS rework_qty,
                    COALESCE((
                        SELECT SUM(st.duration_minutes)
                        FROM production_stops st
                        WHERE st.plan_item_id = i.id
                        {stop_where}
                    ), 0) AS stop_minutes,
                    COALESCE((
                        SELECT SUM(CASE WHEN stt.counts_as_unavailability = 1 THEN st.duration_minutes ELSE 0 END)
                        FROM production_stops st
                        JOIN production_stop_types stt ON stt.id = st.stop_type_id
                        WHERE st.plan_item_id = i.id
                        {stop_where}
                    ), 0) AS unavailability_minutes
                FROM production_plan_items i
                JOIN production_plans p ON p.id = i.plan_id
                JOIN production_products pr ON pr.id = i.product_id
                LEFT JOIN production_stations s ON s.id = i.station_id
                LEFT JOIN production_station_products sp
                  ON sp.station_id = i.station_id
                 AND sp.product_id = i.product_id
                 AND sp.is_active = 1
                WHERE {where_items}
                ORDER BY i.work_day, pr.name, s.name, i.id""",
            production_params + waste_params + waste_params + stop_params + stop_params + item_params,
        ).fetchall()

        # برای هر ردیف، شاخص‌های کنترلی را در Python محاسبه می‌کنیم تا
        # از تکرار فرمول‌ها در SQL و وابستگی به NULL جلوگیری شود.
        control_rows = []
        totals = {
            "target_qty": 0.0,
            "management_target_qty": 0.0,
            "actual_production": 0.0,
            "waste_qty": 0.0,
            "rework_qty": 0.0,
            "allowed_waste_qty": 0.0,
            "allowed_waste_defined": False,
            "stop_minutes": 0.0,
            "unavailability_minutes": 0.0,
        }

        for row in rows:
            target = float(row["target_qty"] or 0)
            management_target = float(row["management_target_qty"] or 0)
            actual = float(row["actual_production"] or 0)
            waste = float(row["waste_qty"] or 0)
            rework = float(row["rework_qty"] or 0)
            stop_minutes = float(row["stop_minutes"] or 0)
            unavailability_minutes = float(row["unavailability_minutes"] or 0)
            allowed_percent = row["allowed_waste_percent"]
            allowed_percent = float(allowed_percent) if allowed_percent is not None else None
            allowed_qty = (actual * allowed_percent / 100.0) if allowed_percent is not None else None
            actual_waste_percent = (waste / actual * 100.0) if actual > 0 else None
            waste_excess = (waste - allowed_qty) if allowed_qty is not None else None

            item = dict(row)
            item.update({
                "target_qty": target,
                "management_target_qty": management_target,
                "actual_production": actual,
                "waste_qty": waste,
                "rework_qty": rework,
                "stop_minutes": stop_minutes,
                "unavailability_minutes": unavailability_minutes,
                "production_variance": actual - target,
                "allowed_waste_qty": allowed_qty,
                "actual_waste_percent": actual_waste_percent,
                "waste_excess": waste_excess,
            })
            control_rows.append(item)

            totals["target_qty"] += target
            totals["management_target_qty"] += management_target
            totals["actual_production"] += actual
            totals["waste_qty"] += waste
            totals["rework_qty"] += rework
            totals["stop_minutes"] += stop_minutes
            totals["unavailability_minutes"] += unavailability_minutes
            if allowed_qty is not None:
                totals["allowed_waste_qty"] += allowed_qty
                totals["allowed_waste_defined"] = True

        totals["production_variance"] = totals["actual_production"] - totals["target_qty"]
        totals["actual_waste_percent"] = (
            totals["waste_qty"] / totals["actual_production"] * 100.0
            if totals["actual_production"] > 0 else None
        )
        totals["waste_excess"] = (
            totals["waste_qty"] - totals["allowed_waste_qty"]
            if totals["allowed_waste_defined"] else None
        )

        products_rows = db.execute(
            "SELECT id, code, name FROM production_products WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        stations_rows = db.execute(
            "SELECT id, code, name FROM production_stations WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        shifts_rows = db.execute(
            "SELECT id, code, name FROM production_shifts WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        employees_rows = db.execute(
            "SELECT id, personnel_code, full_name FROM production_employees WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()

        filters = {
            "date_from": date_from,
            "date_to": date_to,
            "product_id": product_id_raw,
            "station_id": station_id_raw,
            "shift_id": shift_id_raw,
            "employee_id": employee_id_raw,
        }

        return render_template(
            "production_control.html",
            rows=control_rows,
            totals=totals,
            filters=filters,
            products=products_rows,
            stations=stations_rows,
            shifts=shifts_rows,
            employees=employees_rows,
        )
    except Exception as exc:
        flash(f"گزارش کنترل تولید ایجاد نشد: {exc}", "error")
        return redirect(url_for("production.dashboard"))
    finally:
        db.close()
@roles_required("admin")
def attendance():
    """ثبت و مشاهده حضور و وضعیت نیروی تولید؛ بدون محاسبه زمان مفید/OEE."""
    db = _db()
    try:
        if request.method == "POST":
            attendance_date = request.form.get("attendance_date", "").strip()
            shift_id_raw = request.form.get("shift_id", "").strip()
            employee_id_raw = request.form.get("employee_id", "").strip()
            status = request.form.get("status", "").strip().lower()
            start_at = request.form.get("start_at", "").strip() or None
            end_at = request.form.get("end_at", "").strip() or None
            notes = request.form.get("notes", "").strip() or None

            allowed_statuses = {"present", "absent", "leave", "off"}
            if not attendance_date or not shift_id_raw or not employee_id_raw or status not in allowed_statuses:
                flash("تاریخ، شیفت، پرسنل و وضعیت حضور الزامی است.", "error")
                return redirect(url_for("production.attendance"))

            try:
                shift_id = int(shift_id_raw)
                employee_id = int(employee_id_raw)

                shift = db.execute(
                    "SELECT id FROM production_shifts WHERE id = ? AND is_active = 1",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise ValueError("شیفت انتخاب‌شده معتبر نیست.")

                employee = db.execute(
                    "SELECT id FROM production_employees WHERE id = ? AND is_active = 1",
                    (employee_id,),
                ).fetchone()
                if employee is None:
                    raise ValueError("پرسنل انتخاب‌شده معتبر نیست.")

                if start_at and end_at:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(start_at)
                    end_dt = datetime.fromisoformat(end_at)
                    if end_dt < start_dt:
                        raise ValueError("زمان پایان نمی‌تواند قبل از زمان شروع باشد.")

                db.execute(
                    """INSERT INTO production_attendance
                       (attendance_date,shift_id,employee_id,status,start_at,end_at,notes,created_by)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        attendance_date,
                        shift_id,
                        employee_id,
                        status,
                        start_at,
                        end_at,
                        notes,
                        session.get("user_id"),
                    ),
                )
                db.commit()
                flash("رکورد حضور تولید با موفقیت ثبت شد.", "success")
            except Exception as exc:
                db.rollback()
                flash(f"ثبت حضور انجام نشد: {exc}", "error")
            return redirect(url_for("production.attendance"))

        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        shift_id_raw = request.args.get("shift_id", "").strip()
        employee_id_raw = request.args.get("employee_id", "").strip()

        filters = []
        params = []
        if date_from:
            filters.append("a.attendance_date >= ?")
            params.append(date_from)
        if date_to:
            filters.append("a.attendance_date <= ?")
            params.append(date_to)
        if shift_id_raw:
            try:
                shift_filter = int(shift_id_raw)
                filters.append("a.shift_id = ?")
                params.append(shift_filter)
            except ValueError:
                flash("شیفت فیلترشده معتبر نیست.", "error")
                return redirect(url_for("production.attendance"))
        if employee_id_raw:
            try:
                employee_filter = int(employee_id_raw)
                filters.append("a.employee_id = ?")
                params.append(employee_filter)
            except ValueError:
                flash("پرسنل فیلترشده معتبر نیست.", "error")
                return redirect(url_for("production.attendance"))

        where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""

        rows = db.execute(
            f"""SELECT a.id, a.attendance_date, a.status, a.start_at, a.end_at,
                       a.notes, a.created_at,
                       sh.code AS shift_code, sh.name AS shift_name,
                       e.personnel_code, e.full_name AS employee_name
                FROM production_attendance a
                JOIN production_shifts sh ON sh.id = a.shift_id
                JOIN production_employees e ON e.id = a.employee_id
                {where_sql}
                ORDER BY a.attendance_date DESC, sh.code, e.full_name, a.id DESC""",
            params,
        ).fetchall()

        shifts_rows = db.execute(
            "SELECT id, code, name FROM production_shifts WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        employees_rows = db.execute(
            "SELECT id, personnel_code, full_name FROM production_employees WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()

        return render_template(
            "production_attendance.html",
            rows=rows,
            shifts=shifts_rows,
            employees=employees_rows,
            filters={
                "date_from": date_from,
                "date_to": date_to,
                "shift_id": shift_id_raw,
                "employee_id": employee_id_raw,
            },
        )
    finally:
        db.close()


@production_bp.route("/control")
@roles_required("admin")
def production_control():
    """کنترل تجمیعی برنامه، تولید، ضایعات و دوباره‌کاری؛ بدون محاسبه OEE."""
    db = _db()
    try:
        from datetime import date

        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        product_id_raw = request.args.get("product_id", "").strip()
        station_id_raw = request.args.get("station_id", "").strip()
        shift_id_raw = request.args.get("shift_id", "").strip()
        employee_id_raw = request.args.get("employee_id", "").strip()

        # بازه پیش‌فرض: امروز تا امروز؛ کاربر می‌تواند آن را خالی کند تا همه تاریخ‌ها بررسی شوند.
        if not date_from and not date_to:
            today = date.today().isoformat()
            date_from = today
            date_to = today
        elif date_from and not date_to:
            date_to = date_from
        elif date_to and not date_from:
            date_from = date_to

        def _optional_int(raw, label):
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                raise ValueError(f"{label} نامعتبر است.")

        try:
            product_id = _optional_int(product_id_raw, "محصول")
            station_id = _optional_int(station_id_raw, "ایستگاه")
            shift_id = _optional_int(shift_id_raw, "شیفت")
            employee_id = _optional_int(employee_id_raw, "پرسنل")
            if date_from and date_to and date_from > date_to:
                raise ValueError("تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد.")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("production.production_control"))

        # فقط آیتم‌های برنامه تأییدشده در کنترل مبنا قرار می‌گیرند.
        item_filters = ["p.status = 'approved'"]
        item_params = []

        if date_from:
            item_filters.append("i.work_day >= ?")
            item_params.append(date_from)
        if date_to:
            item_filters.append("i.work_day <= ?")
            item_params.append(date_to)
        if product_id is not None:
            item_filters.append("i.product_id = ?")
            item_params.append(product_id)
        if station_id is not None:
            item_filters.append("i.station_id = ?")
            item_params.append(station_id)

        where_items = " AND ".join(item_filters)

        # فیلترهای رویداد تولید؛ تاریخ رویداد از work_day مستقل نگه داشته می‌شود.
        production_filters = []
        production_params = []
        if date_from:
            production_filters.append("e.production_date >= ?")
            production_params.append(date_from)
        if date_to:
            production_filters.append("e.production_date <= ?")
            production_params.append(date_to)
        if shift_id is not None:
            production_filters.append("e.shift_id = ?")
            production_params.append(shift_id)
        if employee_id is not None:
            production_filters.append("e.employee_id = ?")
            production_params.append(employee_id)

        production_where = (" AND " + " AND ".join(production_filters)) if production_filters else ""

        waste_filters = []
        waste_params = []
        if date_from:
            waste_filters.append("w.production_date >= ?")
            waste_params.append(date_from)
        if date_to:
            waste_filters.append("w.production_date <= ?")
            waste_params.append(date_to)
        if shift_id is not None:
            waste_filters.append("w.shift_id = ?")
            waste_params.append(shift_id)
        if employee_id is not None:
            waste_filters.append("w.employee_id = ?")
            waste_params.append(employee_id)

        waste_where = (" AND " + " AND ".join(waste_filters)) if waste_filters else ""

        stop_filters = []
        stop_params = []
        if date_from:
            stop_filters.append("st.production_date >= ?")
            stop_params.append(date_from)
        if date_to:
            stop_filters.append("st.production_date <= ?")
            stop_params.append(date_to)
        if shift_id is not None:
            stop_filters.append("st.shift_id = ?")
            stop_params.append(shift_id)
        if employee_id is not None:
            stop_filters.append("st.employee_id = ?")
            stop_params.append(employee_id)
        stop_where = (" AND " + " AND ".join(stop_filters)) if stop_filters else ""

        rows = db.execute(
            f"""SELECT
                    i.id AS plan_item_id,
                    i.work_day,
                    i.target_qty,
                    i.management_target_qty,
                    pr.code AS product_code,
                    pr.name AS product_name,
                    s.code AS station_code,
                    s.name AS station_name,
                    sp.allowed_waste_percent,
                    COALESCE((
                        SELECT SUM(e.quantity)
                        FROM production_entries e
                        WHERE e.plan_item_id = i.id
                        {production_where}
                    ), 0) AS actual_production,
                    COALESCE((
                        SELECT SUM(w.quantity)
                        FROM production_waste_entries w
                        WHERE w.plan_item_id = i.id
                          AND w.record_type = 'waste'
                        {waste_where}
                    ), 0) AS waste_qty,
                    COALESCE((
                        SELECT SUM(w.quantity)
                        FROM production_waste_entries w
                        WHERE w.plan_item_id = i.id
                          AND w.record_type = 'rework'
                        {waste_where}
                    ), 0) AS rework_qty,
                    COALESCE((
                        SELECT SUM(st.duration_minutes)
                        FROM production_stops st
                        WHERE st.plan_item_id = i.id
                        {stop_where}
                    ), 0) AS stop_minutes,
                    COALESCE((
                        SELECT SUM(CASE WHEN stt.counts_as_unavailability = 1 THEN st.duration_minutes ELSE 0 END)
                        FROM production_stops st
                        JOIN production_stop_types stt ON stt.id = st.stop_type_id
                        WHERE st.plan_item_id = i.id
                        {stop_where}
                    ), 0) AS unavailability_minutes
                FROM production_plan_items i
                JOIN production_plans p ON p.id = i.plan_id
                JOIN production_products pr ON pr.id = i.product_id
                LEFT JOIN production_stations s ON s.id = i.station_id
                LEFT JOIN production_station_products sp
                  ON sp.station_id = i.station_id
                 AND sp.product_id = i.product_id
                 AND sp.is_active = 1
                WHERE {where_items}
                ORDER BY i.work_day, pr.name, s.name, i.id""",
            production_params + waste_params + waste_params + stop_params + stop_params + item_params,
        ).fetchall()

        # برای هر ردیف، شاخص‌های کنترلی را در Python محاسبه می‌کنیم تا
        # از تکرار فرمول‌ها در SQL و وابستگی به NULL جلوگیری شود.
        control_rows = []
        totals = {
            "target_qty": 0.0,
            "management_target_qty": 0.0,
            "actual_production": 0.0,
            "waste_qty": 0.0,
            "rework_qty": 0.0,
            "allowed_waste_qty": 0.0,
            "allowed_waste_defined": False,
            "stop_minutes": 0.0,
            "unavailability_minutes": 0.0,
        }

        for row in rows:
            target = float(row["target_qty"] or 0)
            management_target = float(row["management_target_qty"] or 0)
            actual = float(row["actual_production"] or 0)
            waste = float(row["waste_qty"] or 0)
            rework = float(row["rework_qty"] or 0)
            stop_minutes = float(row["stop_minutes"] or 0)
            unavailability_minutes = float(row["unavailability_minutes"] or 0)
            allowed_percent = row["allowed_waste_percent"]
            allowed_percent = float(allowed_percent) if allowed_percent is not None else None
            allowed_qty = (actual * allowed_percent / 100.0) if allowed_percent is not None else None
            actual_waste_percent = (waste / actual * 100.0) if actual > 0 else None
            waste_excess = (waste - allowed_qty) if allowed_qty is not None else None

            item = dict(row)
            item.update({
                "target_qty": target,
                "management_target_qty": management_target,
                "actual_production": actual,
                "waste_qty": waste,
                "rework_qty": rework,
                "stop_minutes": stop_minutes,
                "unavailability_minutes": unavailability_minutes,
                "production_variance": actual - target,
                "allowed_waste_qty": allowed_qty,
                "actual_waste_percent": actual_waste_percent,
                "waste_excess": waste_excess,
            })
            control_rows.append(item)

            totals["target_qty"] += target
            totals["management_target_qty"] += management_target
            totals["actual_production"] += actual
            totals["waste_qty"] += waste
            totals["rework_qty"] += rework
            totals["stop_minutes"] += stop_minutes
            totals["unavailability_minutes"] += unavailability_minutes
            if allowed_qty is not None:
                totals["allowed_waste_qty"] += allowed_qty
                totals["allowed_waste_defined"] = True

        totals["production_variance"] = totals["actual_production"] - totals["target_qty"]
        totals["actual_waste_percent"] = (
            totals["waste_qty"] / totals["actual_production"] * 100.0
            if totals["actual_production"] > 0 else None
        )
        totals["waste_excess"] = (
            totals["waste_qty"] - totals["allowed_waste_qty"]
            if totals["allowed_waste_defined"] else None
        )

        products_rows = db.execute(
            "SELECT id, code, name FROM production_products WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        stations_rows = db.execute(
            "SELECT id, code, name FROM production_stations WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        shifts_rows = db.execute(
            "SELECT id, code, name FROM production_shifts WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        employees_rows = db.execute(
            "SELECT id, personnel_code, full_name FROM production_employees WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()

        filters = {
            "date_from": date_from,
            "date_to": date_to,
            "product_id": product_id_raw,
            "station_id": station_id_raw,
            "shift_id": shift_id_raw,
            "employee_id": employee_id_raw,
        }

        return render_template(
            "production_control.html",
            rows=control_rows,
            totals=totals,
            filters=filters,
            products=products_rows,
            stations=stations_rows,
            shifts=shifts_rows,
            employees=employees_rows,
        )
    except Exception as exc:
        flash(f"گزارش کنترل تولید ایجاد نشد: {exc}", "error")
        return redirect(url_for("production.dashboard"))
    finally:
        db.close()

@production_bp.route("/work-calendar", methods=["GET", "POST"])
@roles_required("admin")
def work_calendar():
    """ثبت زمان برنامه‌ریزی‌شده هر شیفت و ایستگاه؛ پایه محاسبه Availability در آینده."""
    db = _db()
    try:
        _ensure_work_calendar_table(db)
        if request.method == "POST":
            work_date = request.form.get("work_date", "").strip()
            shift_id_raw = request.form.get("shift_id", "").strip()
            station_id_raw = request.form.get("station_id", "").strip()
            is_working = 1 if request.form.get("is_working") == "1" else 0
            planned_raw = request.form.get("planned_minutes", "").strip()
            notes = request.form.get("notes", "").strip() or None
            if not work_date or not shift_id_raw or not station_id_raw:
                flash("تاریخ، شیفت و ایستگاه الزامی است.", "error")
                return redirect(url_for("production.work_calendar"))
            try:
                shift_id = int(shift_id_raw); station_id = int(station_id_raw)
                shift = db.execute("SELECT id,start_time,end_time,crosses_midnight FROM production_shifts WHERE id=? AND is_active=1", (shift_id,)).fetchone()
                station = db.execute("SELECT id FROM production_stations WHERE id=? AND is_active=1", (station_id,)).fetchone()
                if shift is None or station is None: raise ValueError("شیفت یا ایستگاه انتخاب‌شده معتبر نیست.")
                planned_minutes = float(planned_raw) if planned_raw else (_shift_minutes(shift["start_time"], shift["end_time"], shift["crosses_midnight"]) if is_working else 0.0)
                if not math.isfinite(planned_minutes) or planned_minutes < 0 or planned_minutes > 1440: raise ValueError("زمان برنامه‌ریزی‌شده باید بین صفر تا 1440 دقیقه باشد.")
                if is_working and planned_minutes <= 0: raise ValueError("برای روز کاری، زمان برنامه‌ریزی‌شده باید بیشتر از صفر باشد.")
                existing = db.execute("SELECT id FROM production_work_calendar WHERE work_date=? AND shift_id=? AND station_id=?", (work_date,shift_id,station_id)).fetchone()
                if existing:
                    db.execute("UPDATE production_work_calendar SET is_working=?,planned_minutes=?,notes=?,created_by=?,created_at=SYSUTCDATETIME() WHERE id=?", (is_working,planned_minutes,notes,session.get("user_id"),existing["id"])); message="تقویم کاری به‌روزرسانی شد."
                else:
                    db.execute("INSERT INTO production_work_calendar (work_date,shift_id,station_id,is_working,planned_minutes,notes,created_by) VALUES (?,?,?,?,?,?,?)", (work_date,shift_id,station_id,is_working,planned_minutes,notes,session.get("user_id"))); message="زمان برنامه‌ریزی‌شده ثبت شد."
                db.commit(); flash(message,"success")
            except Exception as exc:
                db.rollback(); flash(f"ثبت تقویم کاری انجام نشد: {exc}","error")
            return redirect(url_for("production.work_calendar"))
        date_from=request.args.get("date_from","").strip(); date_to=request.args.get("date_to","").strip(); shift_filter=request.args.get("shift_id","").strip(); station_filter=request.args.get("station_id","").strip()
        conditions=[]; params=[]
        if date_from: conditions.append("c.work_date >= ?"); params.append(date_from)
        if date_to: conditions.append("c.work_date <= ?"); params.append(date_to)
        if shift_filter:
            try: params.append(int(shift_filter)); conditions.append("c.shift_id = ?")
            except ValueError: flash("فیلتر شیفت معتبر نیست.","error"); return redirect(url_for("production.work_calendar"))
        if station_filter:
            try: params.append(int(station_filter)); conditions.append("c.station_id = ?")
            except ValueError: flash("فیلتر ایستگاه معتبر نیست.","error"); return redirect(url_for("production.work_calendar"))
        where_sql=("WHERE "+" AND ".join(conditions)) if conditions else ""
        rows=db.execute(f"""SELECT c.id,c.work_date,c.is_working,c.planned_minutes,c.notes,sh.code AS shift_code,sh.name AS shift_name,s.code AS station_code,s.name AS station_name FROM production_work_calendar c JOIN production_shifts sh ON sh.id=c.shift_id JOIN production_stations s ON s.id=c.station_id {where_sql} ORDER BY c.work_date DESC,sh.code,s.name,c.id DESC""",params).fetchall()
        shifts_rows=db.execute("SELECT id,code,name,start_time,end_time,crosses_midnight FROM production_shifts WHERE is_active=1 ORDER BY code").fetchall(); stations_rows=db.execute("SELECT id,code,name FROM production_stations WHERE is_active=1 ORDER BY name").fetchall()
        return render_template("production_work_calendar.html",rows=rows,shifts=shifts_rows,stations=stations_rows,filters={"date_from":date_from,"date_to":date_to,"shift_id":shift_filter,"station_id":station_filter})
    finally:
        db.close()
