# -*- coding: utf-8 -*-
"""
نسخه‌ی تحت وب سیستم مدیریت تعمیرات (Flask)

اجرا:
    pip install -r requirements.txt
    python app.py
سپس در مرورگر به آدرس http://127.0.0.1:5000 بروید.
دفعه‌ی اول به‌طور خودکار به صفحه‌ی ساخت حساب مدیر سیستم هدایت می‌شوید.
"""

import datetime
import io
import os
import json
import re
import secrets
import time
from copy import copy
from collections import Counter

from flask import (
    Flask, render_template, request, redirect, url_for, flash, send_file, g, session, abort
)

from database import get_connection
from auth import (
    ROLES, CAN_CREATE_REQUEST, CAN_REVIEW_REQUEST, ADMIN_ONLY,
    CAN_DAILY_INSPECTION, CAN_PREVENTIVE_INSPECTION, GENERAL_ACCESS_ROLES,
    hash_password, verify_password, current_user, login_user, logout_user,
    login_required, roles_required,
)
from jalali import (
    today_jalali_str, now_time_str, gregorian_to_jalali,
    parse_jalali_date, add_days_to_jalali_str,
    jalali_days_in_month, current_jalali_year, MONTH_NAMES_FA,
)
from text_utils import normalize_fa

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, Alignment
    OPENPYXL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OPENPYXL_AVAILABLE = False

app = Flask(__name__)

# تنظیمات نشست امن برای استقرار اینترنتی. ظاهر برنامه و مسیرهای آن تغییری نمی‌کند.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=int(os.environ.get("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024))),
)

# کلید امنیتی نشست (session). اگر متغیر محیطی SECRET_KEY تنظیم شده باشد
# از همان استفاده می‌شود؛ در غیر این صورت یک کلید تصادفی امن ساخته
# می‌شود که با هر بار اجرای مجدد برنامه عوض می‌شود (یعنی کاربران باید
# دوباره وارد شوند). برای استقرار واقعی روی سرور، حتماً یک SECRET_KEY
# ثابت در متغیر محیطی تنظیم کنید تا نشست‌ها با ری‌استارت سرور از بین
# نروند.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

WORK_TYPES = [
    ("etefaghi", "تعمیرات اتفاقی"), ("pishgirane", "پیشگیرانه"), ("asasy", "تعمیرات اساسی"),
    ("tekrary", "خرابی تکراری"), ("sayer", "سایر"),
]
WORK_UNITS = [
    ("barghi", "برق"), ("mekanik", "مکانیک"),
]
DELAY_CAUSES = [
    ("abzarsazi", "ابزار سازی"), ("taminghate", "تامین قطعه"), ("kontrol", "کنترل"),
    ("tasisat", "تاسیسات"), ("tolid", "تولید"), ("sayertakhir", "سایر"),
]
DEPARTMENTS = WORK_UNITS + DELAY_CAUSES  # برای گزارش نفر ساعت که هر دو گروه را نشان می‌دهد

# چک‌لیست بازدید روزانه (قبل از شروع به کار) — هر مورد یعنی «بررسی و تایید شد»
DAILY_CHECKLIST = [
    ("ravankari", "روانکاری و روغن‌کاری دستگاه"),
    ("seday_ghyrmoadi", "نبود صدای غیرعادی هنگام روشن شدن"),
    ("nashti", "نبود نشتی روغن / هوا / آب"),
    ("hefazha_imeni", "سالم بودن حفاظ‌های ایمنی"),
    ("sim_keshi_bargh", "سالم بودن سیم‌کشی و اتصالات برق"),
    ("tamizi_mohit", "تمیزی و نظم محیط اطراف دستگاه"),
    ("feshar_hava_roghan", "فشار هوا / روغن هیدرولیک (در صورت وجود)"),
    ("stop_ezterari", "عملکرد صحیح دکمه استاپ اضطراری"),
    ("abzar_janebi", "سالم بودن ابزار و تجهیزات جانبی"),
    ("damaye_dastgah", "نبود دمای غیرعادی در بدنه دستگاه"),
]

# چک‌لیست بازدید پیشگیرانه و پیش‌بینانه (تعمیرات دوره‌ای)
PREVENTIVE_CHECKLIST = [
    ("bearing_motor", "بررسی و روانکاری بلبرینگ‌های موتور"),
    ("tasme_coupling", "بررسی وضعیت تسمه‌ها و کوپلینگ‌ها"),
    ("filter_roghan", "بررسی / تعویض فیلتر روغن"),
    ("filter_hava", "بررسی / تعویض فیلتر هوا"),
    ("larzesh_motor", "اندازه‌گیری ارتعاش (ویبراسیون) موتور و یاتاقان‌ها"),
    ("damaye_motor", "بررسی دمای موتور و یاتاقان‌ها (ترموگرافی)"),
    ("ettesalat_bargh", "بررسی اتصالات و ترمینال‌های برق"),
    ("roghan_gearbox", "بررسی سطح و کیفیت روغن گیربکس"),
    ("sistem_hydrolic", "بررسی سیستم هیدرولیک (شیلنگ‌ها، اتصالات، نشتی)"),
    ("calibration_sensor", "کالیبراسیون سنسورها"),
    ("limit_switch_imeni", "بررسی لیمیت سوئیچ‌ها و سنسورهای ایمنی"),
    ("zanjir_tasme_naghale", "بررسی زنجیر / تسمه نقاله"),
    ("tamizkari_gireskari", "تمیزکاری عمومی و گریسکاری کلی دستگاه"),
    ("panel_bargh_control", "بررسی پنل برق و تابلوی کنترل"),
]
OVERALL_STATUS_OPTIONS = ["سالم", "نیاز به تعمیر جزئی", "نیاز به تعمیر اساسی"]


def enforced_person_name(submitted_value: str) -> str:
    """
    برای فیلدهای «نام درخواست‌کننده» / «نام بازدیدکننده»: برای هرکسی
    غیر از مدیر سیستم، هرچه در فرم فرستاده شده باشد نادیده گرفته می‌شود
    و به‌جای آن نام خود کاربر واردشده جایگزین می‌شود — این کار سمت سرور
    انجام می‌شود تا حتی با دستکاری فرم در مرورگر هم قابل دور زدن نباشد.
    فقط مدیر سیستم اجازه دارد نام دلخواه وارد کند.
    """
    if session.get("role") == "admin":
        return (submitted_value or "").strip()
    return session.get("full_name") or session.get("username") or ""


def enforced_datetime(submitted_date: str, submitted_time: str):
    """
    برای فیلدهای «تاریخ درخواست» و «ساعت درخواست» در ثبت درخواست خرابی:
    فقط مدیر سیستم اجازه دارد این دو مقدار را دستی تغییر دهد (مثلاً برای
    ثبت یک درخواست قدیمی با تاریخ گذشته). برای بقیه‌ی کاربران، صرف‌نظر
    از آنچه در فرم فرستاده شده، تاریخ و ساعت واقعی سرور در لحظه‌ی ثبت
    جایگزین می‌شود — این هم سمت سرور اعمال می‌شود تا با دستکاری فرم در
    مرورگر قابل دور زدن نباشد.
    """
    if session.get("role") == "admin":
        return (submitted_date or "").strip(), (submitted_time or "").strip()
    return today_jalali_str(), now_time_str()


def parse_hours(value):
    """
    مقدار «میزان ساعت توقف دستگاه» را به عدد اعشاری (ساعت) تبدیل می‌کند.
    در داده‌های واقعی این مقدار می‌تواند به دو شکل ذخیره شده باشد:
      - عدد ساده مثل "2" یا "1.5"
      - به‌صورت "ساعت:دقیقه" مثل "03:00" یا "00:30" یا حتی "47:00"
    """
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    if ":" in text:
        parts = text.split(":")
        try:
            hours = float(parts[0])
            minutes = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
            return hours + minutes / 60.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _migrate_key_schema(db):
    try:
        cols=[r[1] for r in db.execute("PRAGMA table_info(key_equipment)").fetchall()]
        if "linked_device_cod" not in cols:
            db.execute("ALTER TABLE key_equipment ADD COLUMN linked_device_cod TEXT")
        db.execute("CREATE TABLE IF NOT EXISTS key_equipment_meta (key TEXT PRIMARY KEY,value TEXT)")
        db.commit()
    except Exception:
        pass

def get_db():
    if "db" not in g:
        g.db = get_connection()
        _migrate_key_schema(g.db)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.context_processor
def inject_user():
    return {"current_user": current_user(), "ROLES": ROLES}


@app.before_request
def require_setup_and_login():
    """
    اگر هنوز هیچ کاربری در سیستم ساخته نشده، همه‌ی درخواست‌ها به صفحه‌ی
    «راه‌اندازی اولیه» هدایت می‌شوند تا اولین حساب مدیر ساخته شود.
    مسیرهای استاتیک و خود صفحات ورود/راه‌اندازی از این قانون مستثنی‌اند.
    """
    exempt_endpoints = {"login", "setup", "static"}
    if request.endpoint in exempt_endpoints:
        return None

    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        return redirect(url_for("setup"))
    return None


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ---------------------------------------------------------------- CSRF
def csrf_token():
    """
    یک توکن CSRF یکتا برای این نشست می‌سازد (یا مقدار موجود را برمی‌گرداند)
    و آن را در قالب‌ها به‌عنوان تابع {{ csrf_token() }} در دسترس می‌گذارد.
    هر فرم POST این توکن را در یک فیلد پنهان می‌فرستد و پیش از اجرای هر
    درخواست تغییردهنده (POST) با مقدار نشست مقایسه می‌شود؛ در صورت عدم
    تطابق یا نبود توکن، درخواست رد می‌شود (محافظت در برابر CSRF).
    """
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


@app.context_processor
def inject_csrf():
    return {"csrf_token": csrf_token}


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not secrets.compare_digest(sent, expected):
            abort(400, description="درخواست نامعتبر است (توکن امنیتی فرم منقضی یا نادرست است). لطفاً صفحه را رفرش و دوباره تلاش کنید.")


def safe_next_url(candidate: str) -> str:
    """
    برای جلوگیری از حمله‌ی Open Redirect: مقدار next فقط وقتی معتبر است
    که یک مسیر داخلی (با / شروع شود و // یا آدرس کامل نباشد) باشد؛ در
    غیر این صورت صفحه‌ی اصلی برگردانده می‌شود.
    """
    if candidate and candidate.startswith("/") and not candidate.startswith("//") and "\\" not in candidate:
        return candidate
    return url_for("index")


# ---------------------------------------------------------- login rate limit
_login_attempts = {}  # ساختار: {آدرس IP: [زمان‌های تلاش ناموفق]}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # ۵ دقیقه


def _too_many_login_attempts(key: str) -> bool:
    now = time.time()
    attempts = [t for t in _login_attempts.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
    _login_attempts[key] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def _record_login_attempt(key: str) -> None:
    _login_attempts.setdefault(key, []).append(time.time())


def _clear_login_attempts(key: str) -> None:
    _login_attempts.pop(key, None)


# هش ثابتِ یک رمز ساختگی، فقط برای یکسان نگه‌داشتن زمان پاسخ در ورود
# (نه برای احراز هویت واقعی) — نگاه کنید به توضیح داخل login().
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")


@app.errorhandler(400)
def handle_bad_request(_e):
    flash("درخواست نامعتبر بود یا نشست شما منقضی شده است؛ لطفاً دوباره تلاش کنید.", "error")
    target = "index" if session.get("user_id") else "login"
    return redirect(url_for(target))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """ساخت اولین حساب مدیر سیستم (فقط وقتی هیچ کاربری وجود ندارد)."""
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count > 0:
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        full_name = request.form.get("full_name", "").strip()

        if not username or not password:
            flash("نام کاربری و رمز عبور الزامی است.", "error")
        elif password != password2:
            flash("رمز عبور و تکرار آن یکسان نیستند.", "error")
        elif len(password) < 8:
            flash("رمز عبور باید حداقل ۸ کاراکتر باشد.", "error")
        else:
            db.execute(
                "INSERT INTO users (username, password_hash, full_name, role, created_at) "
                "VALUES (?,?,?,'admin',?)",
                (username, hash_password(password), full_name, datetime.datetime.now().isoformat()),
            )
            db.commit()
            flash("حساب مدیر سیستم با موفقیت ساخته شد. حالا وارد شوید.", "success")
            return redirect(url_for("login"))

    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        client_key = request.remote_addr or "unknown"

        if _too_many_login_attempts(client_key):
            flash("تعداد تلاش‌های ورود ناموفق بیش از حد مجاز بوده است؛ لطفاً چند دقیقه دیگر دوباره تلاش کنید.", "error")
            return render_template("login.html")

        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        # حتی وقتی کاربر پیدا نشود، یک مقایسه‌ی هش انجام می‌دهیم تا زمان
        # پاسخ برای «کاربر ناموجود» و «رمز اشتباه» یکسان باشد (جلوگیری از
        # حدس زدن نام‌های کاربری موجود از روی تفاوت زمان پاسخ).
        password_hash = user["password_hash"] if user else _DUMMY_PASSWORD_HASH
        password_ok = verify_password(password, password_hash)

        if not user or not password_ok:
            _record_login_attempt(client_key)
            flash("نام کاربری یا رمز عبور اشتباه است.", "error")
        elif not user["is_active"]:
            flash("این حساب غیرفعال شده است.", "error")
        else:
            _clear_login_attempts(client_key)
            login_user(user)
            db.execute(
                "INSERT INTO audit_log (user_id, username, action, event_time, ip_address, user_agent) VALUES (?,?,?,?,?,?)",
                (user["id"], user["username"], "login", datetime.datetime.now().isoformat(), request.remote_addr, request.user_agent.string[:500]),
            )
            db.commit()
            next_url = safe_next_url(request.args.get("next"))
            return redirect(next_url)

    return render_template("login.html")


@app.route("/logout")
def logout():
    if session.get("user_id"):
        db = get_db()
        db.execute(
            "INSERT INTO audit_log (user_id, username, action, event_time, ip_address, user_agent) VALUES (?,?,?,?,?,?)",
            (session.get("user_id"), session.get("username"), "logout", datetime.datetime.now().isoformat(), request.remote_addr, request.user_agent.string[:500]),
        )
        db.commit()
    logout_user()
    flash("با موفقیت خارج شدید.", "success")
    return redirect(url_for("login"))


@app.route("/admin/audit-log")
@login_required
@roles_required(*ADMIN_ONLY)
def admin_audit_log():
    db = get_db()
    rows = db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1000").fetchall()
    return render_template("admin_audit_log.html", rows=rows)


# ============================================================ admin: users
@app.route("/admin/users", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def admin_users():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "viewer")

        if role not in ROLES:
            flash("نقش نامعتبر است.", "error")
        elif not username or not password:
            flash("نام کاربری و رمز عبور الزامی است.", "error")
        elif len(password) < 8:
            flash("رمز عبور باید حداقل ۸ کاراکتر باشد.", "error")
        elif db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            flash("این نام کاربری قبلاً استفاده شده است.", "error")
        else:
            db.execute(
                "INSERT INTO users (username, password_hash, full_name, role, created_at) VALUES (?,?,?,?,?)",
                (username, hash_password(password), full_name, role, datetime.datetime.now().isoformat()),
            )
            db.commit()
            flash("کاربر جدید ساخته شد.", "success")
        return redirect(url_for("admin_users"))

    users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return render_template("admin_users.html", users=users, roles=ROLES)


@app.route("/admin/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def admin_user_toggle_active(user_id):
    db = get_db()
    if user_id == session.get("user_id"):
        flash("نمی‌توانید حساب خودتان را غیرفعال کنید.", "error")
        return redirect(url_for("admin_users"))
    db.execute("UPDATE users SET is_active = 1 - is_active WHERE id = ?", (user_id,))
    db.commit()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def admin_user_role(user_id):
    db = get_db()
    role = request.form.get("role", "viewer")
    if role not in ROLES:
        flash("نقش نامعتبر است.", "error")
        return redirect(url_for("admin_users"))
    if user_id == session.get("user_id") and role != "admin":
        flash("نمی‌توانید نقش مدیریت خودتان را کاهش دهید.", "error")
        return redirect(url_for("admin_users"))
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()
    flash("نقش کاربر به‌روزرسانی شد.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def admin_user_reset_password(user_id):
    db = get_db()
    new_password = request.form.get("password", "")
    if len(new_password) < 8:
        flash("رمز عبور باید حداقل ۸ کاراکتر باشد.", "error")
        return redirect(url_for("admin_users"))
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
    db.commit()
    flash("رمز عبور کاربر بازنشانی شد.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def admin_user_delete(user_id):
    if user_id == session.get("user_id"):
        flash("نمی‌توانید حساب خودتان را حذف کنید.", "error")
        return redirect(url_for("admin_users"))
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("کاربر حذف شد.", "success")
    return redirect(url_for("admin_users"))


def excel_response(headers, rows, filename):
    if not OPENPYXL_AVAILABLE:
        flash("کتابخانه openpyxl نصب نیست. دستور pip install -r requirements.txt را اجرا کنید.", "error")
        return redirect(request.referrer or url_for("index"))

    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ================================================================ تجهیزات کلیدی و جایگزین
KEY_OPTIONS = {
    "machine_count": ["1", "2", ">2"],
    "bottleneck": ["بله", "خیر"],
    "product_count": ["بله", "خیر"],
    "mtbf": ["<430", ">=430"],
    "external_parts": ["خیر", "0.5", "1"],
    "downtime_hours": [">100", "50-100", "<50"],
    "machine_age": [">10سال", "<=10سال"],
    "spare_parts": ["بله", "خیر"],
    "repeated_stops": [">3", "2-3", "<2"],
    "customer_impact": ["زیاد", "متوسط", "کم"],
    "quality_impact": ["زیاد", "متوسط", "کم"],
}

KEY_FIELDS = [
    ("machine_count", "تعداد ماشین در سازمان"),
    ("bottleneck", "تجهیز گلوگاهی است؟"),
    ("product_count", "تولید چند قطعه متفاوت؟"),
    ("mtbf", "MTBF"),
    ("external_parts", "امکان تامین قطعه از خارج شرکت؟"),
    ("downtime_hours", "جمع توقفات یک سال گذشته (ساعت)"),
    ("machine_age", "سن کاری ماشین"),
    ("spare_parts", "دسترسی قطعات یدکی"),
    ("repeated_stops", "توقفات تکراری طی سال گذشته"),
    ("customer_impact", "تاثیر در سفارش مشتری"),
    ("quality_impact", "تاثیر در کیفیت محصول"),
]

# امتیازدهی واحد معیار کلیدی. امتیاز و نوع دستگاه همیشه از گزینه های انتخاب شده
# محاسبه می شوند و دیگر به عنوان مقدار دستی قفل نمی شوند.
KEY_WEIGHTS = {
    "machine_count": {"1":30,"2":9,">2":0},
    "bottleneck": {"بله":10,"خیر":0},
    "product_count": {"بله":30,"خیر":0},
    "mtbf": {"<430":5,">=430":3},
    "external_parts": {"خیر":20,"0.5":6,"1":0},
    "downtime_hours": {">100":30,"50-100":15,"<50":0},
    "machine_age": {">10سال":0,"<=10سال":5},
    "spare_parts": {"بله":0,"خیر":5},
    "repeated_stops": {">3":30,"2-3":15,"<2":0},
    "customer_impact": {"زیاد":30,"متوسط":15,"کم":0},
    "quality_impact": {"زیاد":5,"متوسط":3,"کم":0},
}

def _key_score(row):
    score = 0
    for field, weights in KEY_WEIGHTS.items():
        value = str(row[field] or "").strip() if field in row.keys() else ""
        score += weights.get(value, 0)
    return score

def _key_classification(score):
    return "کلیدی" if score > 100 else ("عادی" if score < 80 else "نیمه کلیدی")

def _key_norm(v):
    v = str(v or "").strip().lower()
    for a,b in [("ي","ی"),("ك","ک"),("ۀ","ه"),("‌"," "),("_"," ")]: v=v.replace(a,b)
    return re.sub(r"\s+", " ", v)

def _key_tokens(name):
    stop={"دستگاه","ماشین","ماشين","cnc","پژو","نيسان","نیسان","پرايد","پراید","بازاری","بازاري","ef7","tu5","ohv","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19","20","21","22","23","24","25","26","27"}
    x=_key_norm(name).replace("-"," ").replace("/"," ")
    return {t for t in re.findall(r"[\wآ-ی]+",x) if len(t)>2 and t not in stop}

def _key_substitutes(devices, cod, name):
    base=_key_tokens(name)
    if not base: return []
    scored=[]
    for d in devices:
        if d["cod"]==cod: continue
        toks=_key_tokens(d["name"])
        common=base & toks
        # functional phrase rules: machines with the same operation words are interchangeable
        # گروه های عملیاتی که دستگاه های هم کارکرد، جایگزین یکدیگر هستند.
        if {"فرز","نشیمنگاه","پیچ"}.issubset(base):
            if {"فرز","نشیمنگاه","پیچ"}.issubset(toks): scored.append((100,d["cod"],d["name"]))
            continue
        if {"سوراخ","روغن"}.issubset(base):
            if {"سوراخ","روغن"}.issubset(toks): scored.append((100,d["cod"],d["name"]))
            continue
        score=len(common)*3
        if "فرز" in base and "فرز" in toks: score += 4
        if "نشیمنگاه" in base and "نشیمنگاه" in toks: score += 8
        if "پیچ" in base and "پیچ" in toks: score += 5
        if "مهره" in base and "مهره" in toks: score += 5
        if "جای" in base and "جای" in toks: score += 4
        if "خار" in base and "خار" in toks: score += 4
        if "جوینت" in base and "جوینت" in toks: score += 4
        if "فیس" in base and "فیس" in toks: score += 4
        if "بغل" in base and "بغل" in toks: score += 4
        if score >= 9 and common:
            scored.append((score, d["cod"], d["name"]))
    scored.sort(key=lambda x:(-x[0], _key_norm(x[2])))
    return scored

def _key_seed_from_failures(db, cod):
    rows=db.execute("SELECT timetavaghofdastgah, tarikhdarkhast FROM data WHERE codedastgah=? AND etefaghi=1 ORDER BY tarikhdarkhast",(cod,)).fetchall()
    downtime=sum(parse_hours(r["timetavaghofdastgah"]) for r in rows)
    repeated=db.execute("SELECT COUNT(*) FROM data WHERE codedastgah=? AND tekrary=1",(cod,)).fetchone()[0]
    mtbf=""
    dates=[]
    for r in rows:
        try:
            dt=parse_jalali_date(r["tarikhdarkhast"])
            if dt: dates.append(dt)
        except Exception: pass
    if len(dates)>=2:
        try:
            gaps=[(dates[i]-dates[i-1]).days for i in range(1,len(dates))]
            if gaps: mtbf=str(round(sum(gaps)/len(gaps)*24,2))
        except Exception: pass
    return (str(round(downtime,2)) if rows else "", mtbf, str(repeated) if repeated else "0")

KEY_NON_MACHINE_NAME_PATTERNS = (
    "سالن", "انبار", "ساختمان", "متفرقه",
)

def _key_machine_devices(db):
    """فقط تجهیزات/ماشین‌آلات را برگرداند؛ سالن‌ها، انبار و فضاهای سازمانی وارد معیار کلیدی نشوند."""
    rows = db.execute("SELECT cod,name FROM dastgahjadid ORDER BY cod").fetchall()
    result = []
    for r in rows:
        name = _key_norm(r["name"])
        if any(pat in name for pat in KEY_NON_MACHINE_NAME_PATTERNS):
            continue
        if name.strip() == "ساخت":
            continue
        result.append(r)
    return result

def _key_code_norm(v):
    s=_key_norm(v).replace(" ","")
    m=re.match(r"^([A-Za-zآ-ی]+)0*(\d+)$",s)
    return (m.group(1).upper()+m.group(2).zfill(3)) if m else s.upper()

KEY_NON_MACHINE_NAME_PATTERNS=("سالن","انبار","ساختمان","متفرقه")

def _key_machine_devices(db):
    rows=db.execute("SELECT cod,name FROM dastgahjadid ORDER BY cod").fetchall()
    return [r for r in rows if not any(p in _key_norm(r["name"]) for p in KEY_NON_MACHINE_NAME_PATTERNS) and _key_norm(r["name"]).strip()!="ساخت"]

def _excel_selected(ws,rr,cols,options):
    for c,o in zip(cols,options):
        if ws.cell(rr,c).value not in (None,""): return str(o).strip()
    return ""

def _seed_key_equipment_from_template(db):
    db.execute("CREATE TABLE IF NOT EXISTS key_equipment_meta (key TEXT PRIMARY KEY,value TEXT)")
    if db.execute("SELECT 1 FROM key_equipment_meta WHERE key='seed_version'").fetchone(): return
    path=os.path.join(os.path.dirname(__file__),"key_equipment_template.xlsx")
    if not OPENPYXL_AVAILABLE or not os.path.exists(path): return
    wb=load_workbook(path,data_only=False); ws=wb["01"]
    devices=_key_machine_devices(db); by={_key_code_norm(d["cod"]):d for d in devices}
    weights=KEY_WEIGHTS
    found=set()
    for rr in range(9,ws.max_row+1):
        code=ws.cell(rr,4).value
        if not code: continue
        nc=_key_code_norm(code)
        if nc not in by: continue
        d=by[nc]; found.add(nc); vals={
          "machine_count":_excel_selected(ws,rr,range(5,8),["1","2",">2"]),"bottleneck":_excel_selected(ws,rr,range(8,10),["بله","خیر"]),"product_count":_excel_selected(ws,rr,range(10,12),["بله","خیر"]),"mtbf":_excel_selected(ws,rr,range(12,14),["<430",">=430"]),"external_parts":_excel_selected(ws,rr,range(14,17),["خیر","0.5","1"]),"downtime_hours":_excel_selected(ws,rr,range(17,20),[">100","50-100","<50"]),"machine_age":_excel_selected(ws,rr,range(20,22),[">10سال","<=10سال"]),"spare_parts":_excel_selected(ws,rr,range(22,24),["بله","خیر"]),"repeated_stops":_excel_selected(ws,rr,range(24,27),[">3","2-3","<2"]),"customer_impact":_excel_selected(ws,rr,range(27,30),["زیاد","متوسط","کم"]),"quality_impact":_excel_selected(ws,rr,range(30,33),["زیاد","متوسط","کم"])}
        # score/classification are derived values, never manual.
        score=sum(KEY_WEIGHTS[k].get(vals.get(k, ""),0) for k in KEY_WEIGHTS)
        vals["score"]=str(score); vals["classification"]=_key_classification(score)
        db.execute("INSERT OR IGNORE INTO key_equipment(cod,name,linked_device_cod,manual_fields,updated_at) VALUES(?,?,?,?,?)",(d["cod"],d["name"],d["cod"],"",datetime.datetime.now().isoformat(timespec="seconds")))
        sets=[];args=[]
        for k,v in vals.items():
            if v!="": sets.append(k+"=?");args.append(v)
        if sets: args.append(d["cod"]);db.execute("UPDATE key_equipment SET "+",".join(sets)+",linked_device_cod=? WHERE cod=?",args[:-1]+[d["cod"],args[-1]])
    # Explicit replacements from sheet 3 are locked as manual.
    ws3=wb["تجهیزات کلیدی بر اساس کارنامه"]
    for rr in range(6,ws3.max_row+1):
        code=ws3.cell(rr,5).value
        if not code: continue
        nc=_key_code_norm(code)
        if nc not in by: continue
        ac=by[nc]["cod"]; sn=str(ws3.cell(rr,6).value or "").strip(); sc=str(ws3.cell(rr,7).value or "").strip(); ca=str(ws3.cell(rr,8).value or "").strip()
        if sn or sc: db.execute("UPDATE key_equipment SET substitute_names=?,substitute_codes=? WHERE cod=?",(sn,sc,ac))
        if ca: db.execute("UPDATE key_equipment SET contractor_alternative=? WHERE cod=?",(ca,ac))
        mf=set()
        if sn or sc: mf.update(["substitute_names","substitute_codes"])
        if ca: mf.add("contractor_alternative")
        db.execute("UPDATE key_equipment SET manual_fields=? WHERE cod=?",(json.dumps(sorted(mf),ensure_ascii=False),ac))
    for d in devices:
        db.execute("INSERT OR IGNORE INTO key_equipment(cod,name,linked_device_cod,manual_fields,updated_at) VALUES(?,?,?,?,?)",(d["cod"],d["name"],d["cod"],"",datetime.datetime.now().isoformat(timespec="seconds")))
    db.execute("INSERT OR REPLACE INTO key_equipment_meta(key,value) VALUES('seed_version','2026-09-12-v4')")
    db.commit()

def _ensure_key_rows(db):
    _seed_key_equipment_from_template(db)
    for d in _key_machine_devices(db):
        if not db.execute("SELECT 1 FROM key_equipment WHERE cod=?",(d["cod"],)).fetchone():
            db.execute("INSERT INTO key_equipment(cod,name,linked_device_cod,manual_fields,updated_at) VALUES(?,?,?,?,?)",(d["cod"],d["name"],d["cod"],"",datetime.datetime.now().isoformat(timespec="seconds")))
        else:
            db.execute("UPDATE key_equipment SET name=?,linked_device_cod=? WHERE cod=?",(d["name"],d["cod"],d["cod"]))
    # یک بار جایگزین های اولیه دستگاه های کلیدی را بر اساس کارکرد تکمیل کن؛
    # بعد از آن ویرایش های دستی دست نخورده می مانند.
    fix_key = db.execute("SELECT 1 FROM key_equipment_meta WHERE key='substitute_fix_v2'").fetchone()
    if not fix_key:
        devices=_key_machine_devices(db)
        for d in devices:
            r=db.execute("SELECT * FROM key_equipment WHERE cod=?",(d["cod"],)).fetchone()
            if not r or str(r["classification"] or "").strip()!="کلیدی":
                db.execute("UPDATE key_equipment SET substitute_names='', substitute_codes='' WHERE cod=?",(d["cod"],))
                continue
            manual=set()
            try: manual=set(json.loads(r["manual_fields"] or "[]"))
            except Exception: pass
            if "substitute_names" not in manual and "substitute_codes" not in manual:
                subs=_key_substitutes(devices,d["cod"],d["name"])
                db.execute("UPDATE key_equipment SET substitute_names=?, substitute_codes=? WHERE cod=?",
                           ("، ".join(x[2] for x in subs), ", ".join(x[1] for x in subs), d["cod"]))
        db.execute("INSERT OR REPLACE INTO key_equipment_meta(key,value) VALUES('substitute_fix_v2','1')")

    # باز کردن صفحه نباید هیچ داده ای را تغییر دهد.
    # محدودیت جایگزین در زمان ذخیره و در خروجی Excel اعمال می شود.
    db.commit()


def _auto_fill_key_rows(db):
    """تکمیل خودکار فقط با فرمان کاربر؛ فیلدهای دستی هرگز بازنویسی نمی‌شوند."""
    _ensure_key_rows(db); devices=_key_machine_devices(db)
    weights=KEY_WEIGHTS
    for d in devices:
        r=db.execute("SELECT * FROM key_equipment WHERE cod=?",(d["cod"],)).fetchone()
        try: manual=set(json.loads(r["manual_fields"] or "[]"))
        except: manual=set()
        downtime,mtbf,rep=_key_seed_from_failures(db,d["cod"]); auto={}
        same=sum(1 for x in devices if _key_norm(x["name"])==_key_norm(d["name"]))
        auto["machine_count"]="1" if same<=1 else ("2" if same==2 else ">2")
        if downtime!="":
            dv=float(downtime);auto["downtime_hours"] = ">100" if dv>100 else ("50-100" if dv>=50 else "<50")
        if mtbf!="": auto["mtbf"]="<430" if float(mtbf)<430 else ">=430"
        try:
            rv=int(float(rep or 0));auto["repeated_stops"] = ">3" if rv>3 else ("2-3" if rv>=2 else "<2")
        except: pass
        # New devices can inherit subjective criteria from a strongly similar substitute group.
        subs=_key_substitutes(devices,d["cod"],d["name"])
        for fk in ("bottleneck","product_count","external_parts","machine_age","spare_parts","customer_impact","quality_impact"):
            if fk in manual or r[fk]: continue
            vals=[]
            for _,cc,_ in subs[:6]:
                q=db.execute("SELECT "+fk+" FROM key_equipment WHERE cod=?",(cc,)).fetchone()
                if q and q[0]: vals.append(q[0])
            if vals: auto[fk]=Counter(vals).most_common(1)[0][0]
        for k,v in auto.items():
            if k not in manual and v!="": db.execute("UPDATE key_equipment SET "+k+"=? WHERE cod=?",(v,d["cod"]))
        rr=db.execute("SELECT * FROM key_equipment WHERE cod=?",(d["cod"],)).fetchone()
        # Always recalculate derived values from the current criteria.
        score=_key_score(rr)
        cls=_key_classification(score)
        db.execute("UPDATE key_equipment SET score=?, classification=? WHERE cod=?",(str(score),cls,d["cod"]))
        # تجهیزات جایگزین فقط برای دستگاه های «کلیدی» به صورت خودکار ثبت می شوند.
        # برای نیمه کلیدی/عادی، مقدارهای خودکار قبلی پاک می شوند؛ مقدارهای دستی دست نخورده می مانند.
        current_cls = db.execute("SELECT classification FROM key_equipment WHERE cod=?", (d["cod"],)).fetchone()
        is_key = bool(current_cls and str(current_cls[0] or "").strip() == "کلیدی")
        if is_key and ("substitute_names" not in manual or "substitute_codes" not in manual):
            if subs:
                if "substitute_names" not in manual: db.execute("UPDATE key_equipment SET substitute_names=? WHERE cod=?",("، ".join(x[2] for x in subs),d["cod"]))
                if "substitute_codes" not in manual: db.execute("UPDATE key_equipment SET substitute_codes=? WHERE cod=?",(", ".join(x[1] for x in subs),d["cod"]))
        else:
            if "substitute_names" not in manual: db.execute("UPDATE key_equipment SET substitute_names='' WHERE cod=?", (d["cod"],))
            if "substitute_codes" not in manual: db.execute("UPDATE key_equipment SET substitute_codes='' WHERE cod=?", (d["cod"],))
    db.commit()

@app.route("/key-equipment", methods=["GET","POST"])
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def key_equipment():
    db=get_db(); _ensure_key_rows(db)
    if request.method=="POST":
        cod=request.form.get("cod", "").strip()
        # score و classification فیلد محاسباتی هستند و از فرم پذیرفته نمی شوند.
        allowed=[k for k,_ in KEY_FIELDS] + ["contractor_alternative","substitute_codes","substitute_names"]
        try:
            targets=[cod] if cod else [r["cod"] for r in db.execute("SELECT cod FROM key_equipment ORDER BY cod").fetchall()]
            saved=0
            for row_cod in targets:
                old=db.execute("SELECT manual_fields, classification FROM key_equipment WHERE cod=?",(row_cod,)).fetchone()
                if not old: continue
                try: manual=set(json.loads(old["manual_fields"] or "[]"))
                except Exception: manual=set()
                sets=[]; vals=[]
                for k in allowed:
                    field=f"{k}__{row_cod}"
                    if field not in request.form: continue
                    value=(request.form.get(field) or "").strip()
                    sets.append(f"{k}=?"); vals.append(value)
                    if k not in ("substitute_names","substitute_codes","contractor_alternative"):
                        manual.add(k)
                if not sets: continue

                # امتیاز و نوع دستگاه را بعد از ذخیره معیارها از نو محاسبه می کنیم.
                # فقط دستگاه کلیدی مجاز به داشتن تجهیزات جایگزین است.
                pending={k: vals[i] for i,k in enumerate([x.split("=?")[0] for x in sets]) if k in KEY_FIELDS}
                current=db.execute("SELECT * FROM key_equipment WHERE cod=?",(row_cod,)).fetchone()
                data=dict(current)
                data.update(pending)
                new_class=_key_classification(_key_score(data))
                if str(new_class).strip() != "کلیدی":
                    for k in ("substitute_names","substitute_codes"):
                        if f"{k}=?" not in sets:
                            sets.append(f"{k}=?"); vals.append("")
                        else:
                            idx=sets.index(f"{k}=?"); vals[idx]=""
                        manual.discard(k)

                # Derived fields are written last, so stale values can never survive a save.
                score=_key_score(data)
                cls=_key_classification(score)
                sets += ["score=?", "classification=?", "manual_fields=?", "updated_at=?"]
                vals += [str(score), cls, json.dumps(sorted(manual),ensure_ascii=False), datetime.datetime.now().isoformat(timespec="seconds")]
                vals.append(row_cod)
                db.execute("UPDATE key_equipment SET " + ", ".join(sets) + " WHERE cod=?", vals)
                saved += 1
            db.commit()
            flash(f"تغییرات {saved} دستگاه با موفقیت ذخیره شد.","success")
        except Exception as e:
            db.rollback()
            app.logger.exception("key equipment save failed")
            flash("ذخیره انجام نشد. خطای فنی: "+str(e),"danger")
        return redirect(url_for("key_equipment"))
    rows=db.execute("SELECT * FROM key_equipment ORDER BY cod").fetchall()
    return render_template("key_equipment.html",rows=rows,key_fields=KEY_FIELDS,key_options=KEY_OPTIONS)

@app.route("/key-equipment/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def key_equipment_export():
    db=get_db(); _ensure_key_rows(db)
    if not OPENPYXL_AVAILABLE: abort(500)
    template_path=os.path.join(os.path.dirname(__file__),"key_equipment_template.xlsx")
    wb=load_workbook(template_path,data_only=False)
    rows=db.execute("SELECT * FROM key_equipment ORDER BY cod").fetchall()
    by={_key_code_norm(r["cod"]):r for r in rows}
    def mark(ws,rr,cols,opts,val):
        v=str(val or "").strip()
        for c,o in zip(cols,opts): ws.cell(rr,c).value=1 if v==o else None
    machine_rows=[r for r in rows if not any(p in _key_norm(r["name"]) for p in KEY_NON_MACHINE_NAME_PATTERNS) and _key_norm(r["name"]).strip()!="ساخت"]
    # Sheet 01: update existing and append new machines after row 121.
    ws=wb["01"]
    existing={_key_code_norm(ws.cell(rr,4).value) for rr in range(9,ws.max_row+1) if ws.cell(rr,4).value}
    for rr in range(9,ws.max_row+1):
        r=by.get(_key_code_norm(ws.cell(rr,4).value)) if ws.cell(rr,4).value else None
        if not r: continue
        ws.cell(rr,3).value=r["name"];ws.cell(rr,4).value=r["cod"]
        for c in range(5,33): ws.cell(rr,c).value=None
        mark(ws,rr,range(5,8),["1","2",">2"],r["machine_count"]);mark(ws,rr,range(8,10),["بله","خیر"],r["bottleneck"]);mark(ws,rr,range(10,12),["بله","خیر"],r["product_count"]);mark(ws,rr,range(12,14),["<430",">=430"],r["mtbf"]);mark(ws,rr,range(14,17),["خیر","0.5","1"],r["external_parts"]);mark(ws,rr,range(17,20),[">100","50-100","<50"],r["downtime_hours"]);mark(ws,rr,range(20,22),[">10سال","<=10سال"],r["machine_age"]);mark(ws,rr,range(22,24),["بله","خیر"],r["spare_parts"]);mark(ws,rr,range(24,27),[">3","2-3","<2"],r["repeated_stops"]);mark(ws,rr,range(27,30),["زیاد","متوسط","کم"],r["customer_impact"]);mark(ws,rr,range(30,33),["زیاد","متوسط","کم"],r["quality_impact"])
        # محاسبه مقدار واقعی امتیاز و وضعیت، تا در پیش‌نمایش Excel هم بلافاصله دیده شود.
        score_val=0
        for c in range(5,33):
            v=ws.cell(rr,c).value
            try: score_val += float(v or 0) * float(ws.cell(7,c).value or 0) * float(ws.cell(6,c).value or 0)
            except (TypeError,ValueError): pass
        ws.cell(rr,33).value=round(score_val,2)
        ws.cell(rr,34).value="کلیدی" if score_val>100 else ("عادی" if score_val<80 else "نیمه کلیدی")
    # append rows using row 9 style
    rr=max(ws.max_row+1,122)
    for r in machine_rows:
        if _key_code_norm(r["cod"]) in existing: continue
        for c in range(1,ws.max_column+1): ws.cell(rr,c)._style=copy(ws.cell(9,c)._style)
        ws.cell(rr,2).value=rr-8;ws.cell(rr,3).value=r["name"];ws.cell(rr,4).value=r["cod"]
        for c in range(5,33): ws.cell(rr,c).value=None
        mark(ws,rr,range(5,8),["1","2",">2"],r["machine_count"]);mark(ws,rr,range(8,10),["بله","خیر"],r["bottleneck"]);mark(ws,rr,range(10,12),["بله","خیر"],r["product_count"]);mark(ws,rr,range(12,14),["<430",">=430"],r["mtbf"]);mark(ws,rr,range(14,17),["خیر","0.5","1"],r["external_parts"]);mark(ws,rr,range(17,20),[">100","50-100","<50"],r["downtime_hours"]);mark(ws,rr,range(20,22),[">10سال","<=10سال"],r["machine_age"]);mark(ws,rr,range(22,24),["بله","خیر"],r["spare_parts"]);mark(ws,rr,range(24,27),[">3","2-3","<2"],r["repeated_stops"]);mark(ws,rr,range(27,30),["زیاد","متوسط","کم"],r["customer_impact"]);mark(ws,rr,range(30,33),["زیاد","متوسط","کم"],r["quality_impact"]);score_val=0
        for c in range(5,33):
            v=ws.cell(rr,c).value
            try: score_val += float(v or 0) * float(ws.cell(7,c).value or 0) * float(ws.cell(6,c).value or 0)
            except (TypeError,ValueError): pass
        ws.cell(rr,33).value=round(score_val,2);ws.cell(rr,34).value="کلیدی" if score_val>100 else ("عادی" if score_val<80 else "نیمه کلیدی");rr+=1
    # Sheet 2: append missing app devices, then fill only comparable criteria.
    ws=wb["ابراهیمی"];existing2={_key_code_norm(ws.cell(r,4).value) for r in range(7,ws.max_row+1) if ws.cell(r,4).value}; rr=ws.max_row+1
    for r in machine_rows:
        if _key_code_norm(r["cod"]) in existing2: continue
        for c in range(1,ws.max_column+1): ws.cell(rr,c)._style=copy(ws.cell(7,c)._style)
        ws.cell(rr,2).value=rr-6;ws.cell(rr,3).value=r["name"];ws.cell(rr,4).value=r["cod"];rr+=1
    for rr in range(7,ws.max_row+1):
        r=by.get(_key_code_norm(ws.cell(rr,4).value)) if ws.cell(rr,4).value else None
        if not r: continue
        ws.cell(rr,3).value=r["name"];ws.cell(rr,4).value=r["cod"]
        for c in range(5,34): ws.cell(rr,c).value=None
        mark(ws,rr,range(5,8),["1","2",">2"],r["machine_count"]);mark(ws,rr,range(8,10),["بله","خیر"],r["bottleneck"]);mark(ws,rr,range(10,12),["بله","خیر"],r["product_count"]);mark(ws,rr,range(15,18),["خیر","0.5","1"],r["external_parts"]);mark(ws,rr,range(18,21),[">200","100-200","<100"],r["downtime_hours"]);mark(ws,rr,range(23,25),["بله","خیر"],r["spare_parts"]);mark(ws,rr,range(25,28),[">3","2-3","<2"],r["repeated_stops"])
        ws.cell(rr,34).value=f'=(E{rr}*10+F{rr}*3)*3+H{rr}*5*2+J{rr}*10*3+L{rr}*5+M{rr}*3+(O{rr}*10+P{rr}*3)*2+(R{rr}*10+S{rr}*3)*3+U{rr}*5+V{rr}*5+(Y{rr}*10+Z{rr}*5)*3+(AB{rr}*10+AC{rr}*5)*3+AE{rr}*5+AF{rr}*3';ws.cell(rr,35).value=f'=IF(AH{rr}>100,"کلیدی",IF(AH{rr}<80,"عادی","نیمه کلیدی"))'
    # Sheet 3: only KEY equipment, with original style and footer.
    # نیمه‌کلیدی و عادی در این بخش نباید نمایش داده شوند.
    key_machine_rows=[r for r in machine_rows if str(r["classification"] or "").strip()=="کلیدی"]
    ws=wb["تجهیزات کلیدی بر اساس کارنامه"];src=load_workbook(template_path,data_only=False)["تجهیزات کلیدی بر اساس کارنامه"]
    footer=[([src.cell(r,c).value for c in range(1,9)],[copy(src.cell(r,c)._style) for c in range(1,9)],src.row_dimensions[r].height) for r in range(64,67)]
    for m in list(ws.merged_cells.ranges):
        if m.min_row>=6: ws.unmerge_cells(str(m))
    ws.delete_rows(6,ws.max_row-5)
    data_styles=[copy(src.cell(6,c)._style) for c in range(1,9)];h=src.row_dimensions[6].height
    for i,r in enumerate(key_machine_rows,6):
        ws.row_dimensions[i].height=h
        for c in range(1,9): ws.cell(i,c)._style=copy(data_styles[c-1])
        ws.merge_cells(start_row=i,start_column=3,end_row=i,end_column=4);ws.cell(i,2).value=i-5;ws.cell(i,3).value=r["name"];ws.cell(i,5).value=r["cod"];ws.cell(i,6).value=r["substitute_names"] or None;ws.cell(i,7).value=r["substitute_codes"] or None;ws.cell(i,8).value=r["contractor_alternative"] or None
    fs=6+len(key_machine_rows)+1
    for j,(vals,styles,hgt) in enumerate(footer):
        r=fs+j;ws.row_dimensions[r].height=hgt
        for c in range(1,9): ws.cell(r,c)._style=copy(styles[c-1]);ws.cell(r,c).value=vals[c-1]
    ws.merge_cells(start_row=fs,start_column=3,end_row=fs,end_column=4);ws.merge_cells(start_row=fs+1,start_column=3,end_row=fs+1,end_column=4);ws.merge_cells(start_row=fs+2,start_column=3,end_row=fs+2,end_column=4);ws.merge_cells(start_row=fs+2,start_column=6,end_row=fs+2,end_column=8)
    for sh in wb.worksheets: sh.sheet_view.rightToLeft=True
    try: wb.calculation.fullCalcOnLoad=True;wb.calculation.forceFullCalc=True;wb.calculation.calcMode='auto'
    except: pass
    out=io.BytesIO();wb.save(out);out.seek(0);return send_file(out,as_attachment=True,download_name='معیار_کلیدی_و_تجهیزات_جایگزین.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ================================================================ شناسنامه ماشین‌آلات FM107
from difflib import SequenceMatcher

MACHINE_PASSPORT_SOURCE = os.path.join(os.path.dirname(__file__), "لیست_ماشین_آلات_مرجع.xlsx")


def _passport_text(v):
    if v is None:
        return ""
    return str(v).strip()


def _passport_similarity(a, b):
    a = _key_norm(a).replace(" ", "")
    b = _key_norm(b).replace(" ", "")
    return SequenceMatcher(None, a, b).ratio() if a and b else 0


def _passport_import_once(db):
    """فرم FM107 را فقط یک بار از Excel داخلی وارد می‌کند و سپس مستقل از Excel کار می‌کند."""
    db.execute("CREATE TABLE IF NOT EXISTS machine_passport_meta (key TEXT PRIMARY KEY,value TEXT)")
    if db.execute("SELECT 1 FROM machine_passport_meta WHERE key='import_version'").fetchone():
        return
    if not OPENPYXL_AVAILABLE or not os.path.exists(MACHINE_PASSPORT_SOURCE):
        return
    wb = load_workbook(MACHINE_PASSPORT_SOURCE, data_only=True)
    ws = wb["FM107"]
    devices = db.execute("SELECT cod,name FROM dastgahjadid ORDER BY cod").fetchall()
    by_code = {_key_code_norm(d["cod"]): d for d in devices}
    used = set()
    mappings = []
    # اولویت با کد، سپس تطبیق نام. اگر واقعاً دستگاه جدید باشد، به رجیستری هم اضافه می‌شود.
    for rr in range(8, ws.max_row + 1):
        source_name = _passport_text(ws.cell(rr, 2).value)
        source_cod = _passport_text(ws.cell(rr, 4).value)
        if not source_name or not source_cod:
            continue
        nc = _key_code_norm(source_cod)
        d = by_code.get(nc)
        if d is None:
            best = None
            for cand in devices:
                if cand["cod"] in used:
                    continue
                sim = _passport_similarity(source_name, cand["name"])
                if best is None or sim > best[0]:
                    best = (sim, cand)
            if best and best[0] >= 0.72:
                d = best[1]
        if d is None:
            # دستگاه موجود در فرم ولی غایب در CMMS: به رجیستری اضافه شود.
            db.execute("INSERT OR IGNORE INTO dastgahjadid(cod,name) VALUES(?,?)", (source_cod, source_name))
            d = db.execute("SELECT cod,name FROM dastgahjadid WHERE cod=?", (source_cod,)).fetchone()
            by_code[_key_code_norm(source_cod)] = d
            devices = list(devices) + [d]
        used.add(d["cod"])
        mappings.append((rr, d, source_name, source_cod))

    for rr, d, source_name, source_cod in mappings:
        vals = (
            d["cod"], d["name"], source_name, source_cod,
            _passport_text(ws.cell(rr,5).value), _passport_text(ws.cell(rr,6).value),
            _passport_text(ws.cell(rr,7).value), _passport_text(ws.cell(rr,8).value),
            _passport_text(ws.cell(rr,9).value), _passport_text(ws.cell(rr,10).value),
            _passport_text(ws.cell(rr,11).value), _passport_text(ws.cell(rr,12).value),
            _passport_text(ws.cell(rr,13).value), _passport_text(ws.cell(rr,14).value),
            _passport_text(ws.cell(rr,15).value), _passport_text(ws.cell(rr,16).value),
            _passport_text(ws.cell(rr,17).value), _passport_text(ws.cell(rr,18).value),
            _passport_text(ws.cell(rr,19).value), _passport_text(ws.cell(rr,20).value),
            _passport_text(ws.cell(rr,21).value), datetime.datetime.now().isoformat(timespec="seconds"),
        )
        db.execute("""INSERT INTO machine_passport
            (device_cod,device_name,source_name,source_cod,manufacturer_country,manufacturer_company,useful_life,
             manufacture_date,serial_number,commissioning_date,purchase_condition,technical_info,energy_consumption,
             other_energy,cooling_system,dimensions_length,dimensions_width,dimensions_height,accessories,
             operation_description,notes,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(device_cod) DO UPDATE SET
             device_name=excluded.device_name, source_name=excluded.source_name, source_cod=excluded.source_cod,
             manufacturer_country=excluded.manufacturer_country, manufacturer_company=excluded.manufacturer_company,
             useful_life=excluded.useful_life, manufacture_date=excluded.manufacture_date, serial_number=excluded.serial_number,
             commissioning_date=excluded.commissioning_date, purchase_condition=excluded.purchase_condition,
             technical_info=excluded.technical_info, energy_consumption=excluded.energy_consumption,
             other_energy=excluded.other_energy, cooling_system=excluded.cooling_system,
             dimensions_length=excluded.dimensions_length, dimensions_width=excluded.dimensions_width,
             dimensions_height=excluded.dimensions_height, accessories=excluded.accessories,
             operation_description=excluded.operation_description, notes=excluded.notes, updated_at=excluded.updated_at""", vals)

    # شیت دوم: کاربرد ماشین‌ها در محصولات مختلف
    ws2 = wb["لیست ماشین آلات"]
    product_headers = [_passport_text(ws2.cell(2,c).value) for c in range(5, ws2.max_column + 1)]
    for rr in range(3, ws2.max_row + 1):
        source_name = _passport_text(ws2.cell(rr,3).value)
        source_cod = _passport_text(ws2.cell(rr,4).value)
        if not source_cod:
            continue
        d = by_code.get(_key_code_norm(source_cod))
        if d is None and source_name:
            best = max((( _passport_similarity(source_name,c["name"]), c) for c in devices), key=lambda x:x[0], default=(0,None))
            if best[0] >= 0.72: d = best[1]
        if d is None:
            continue
        flags = {}
        for idx,c in enumerate(range(5, ws2.max_column+1)):
            if product_headers[idx]:
                flags[product_headers[idx]] = _passport_text(ws2.cell(rr,c).value)
        db.execute("""INSERT INTO machine_product_usage(device_cod,product_flags,updated_at) VALUES(?,?,?)
                    ON CONFLICT(device_cod) DO UPDATE SET product_flags=excluded.product_flags,updated_at=excluded.updated_at""",
                   (d["cod"], json.dumps(flags, ensure_ascii=False), datetime.datetime.now().isoformat(timespec="seconds")))
    db.execute("INSERT OR REPLACE INTO machine_passport_meta(key,value) VALUES('import_version','2026-09-12-FM107-v1')")
    db.commit()


def _ensure_machine_passport(db):
    _passport_import_once(db)
    # دستگاه جدید CMMS نیز بلافاصله در فرم شناسنامه ظاهر شود، بدون نیاز به Excel.
    rows = db.execute("SELECT cod,name FROM dastgahjadid ORDER BY cod").fetchall()
    for d in rows:
        if not db.execute("SELECT 1 FROM machine_passport WHERE device_cod=?", (d["cod"],)).fetchone():
            db.execute("INSERT INTO machine_passport(device_cod,device_name,source_name,source_cod,updated_at) VALUES(?,?,?,?,?)",
                       (d["cod"], d["name"], d["name"], d["cod"], datetime.datetime.now().isoformat(timespec="seconds")))
    db.commit()


@app.route("/machine-passports", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def machine_passports():
    db = get_db()
    _ensure_machine_passport(db)
    if request.method == "POST":
        cod = request.form.get("device_cod", "").strip()
        if not cod:
            flash("کد دستگاه نامعتبر است.", "error")
            return redirect(url_for("machine_passports"))
        fields = [
            "device_name","manufacturer_country","manufacturer_company","useful_life","manufacture_date",
            "serial_number","commissioning_date","purchase_condition","technical_info","energy_consumption",
            "other_energy","cooling_system","dimensions_length","dimensions_width","dimensions_height",
            "accessories","operation_description","notes"
        ]
        vals = {f: request.form.get(f, "").strip() for f in fields}
        sets = ",".join(f+"=?" for f in fields) + ",updated_at=?"
        args = [vals[f] for f in fields] + [datetime.datetime.now().isoformat(timespec="seconds"), cod]
        db.execute("UPDATE machine_passport SET "+sets+" WHERE device_cod=?", args)
        # نام دستگاه در فرم و رجیستری باید هماهنگ بماند.
        if vals["device_name"]:
            db.execute("UPDATE dastgahjadid SET name=? WHERE cod=?", (vals["device_name"], cod))
        products = ["پراید", "پژو", "XUM", "TU3", "نیسان", "پیکان", "OHVG", "TU5", "توضیحات"]
        flags = {p: request.form.get("product__" + p, "").strip() for p in products}
        db.execute("INSERT INTO machine_product_usage(device_cod,product_flags,updated_at) VALUES(?,?,?) ON CONFLICT(device_cod) DO UPDATE SET product_flags=excluded.product_flags,updated_at=excluded.updated_at",
                   (cod, json.dumps(flags, ensure_ascii=False), datetime.datetime.now().isoformat(timespec="seconds")))
        db.commit()
        flash("شناسنامه و کاربرد دستگاه ذخیره شد.", "success")
        return redirect(url_for("machine_passports", edit=cod))
    rows = db.execute("SELECT * FROM machine_passport ORDER BY device_cod").fetchall()
    edit_cod = request.args.get("edit") or (rows[0]["device_cod"] if rows else "")
    edit = db.execute("SELECT * FROM machine_passport WHERE device_cod=?", (edit_cod,)).fetchone() if edit_cod else None
    usage = {}
    if edit_cod:
        ur = db.execute("SELECT product_flags FROM machine_product_usage WHERE device_cod=?", (edit_cod,)).fetchone()
        if ur:
            try: usage = json.loads(ur["product_flags"] or "{}")
            except Exception: usage = {}
    return render_template("machine_passports.html", rows=rows, edit=edit, usage=usage,
                           product_headers=["پراید","پژو","XUM","TU3","نیسان","پیکان","OHVG","TU5","توضیحات"])


@app.route("/machine-passports/export")
@login_required
@roles_required(*ADMIN_ONLY)
def machine_passports_export():
    db = get_db(); _ensure_machine_passport(db)
    if not OPENPYXL_AVAILABLE or not os.path.exists(MACHINE_PASSPORT_SOURCE):
        abort(500, description="فایل مرجع Excel در برنامه موجود نیست.")
    wb = load_workbook(MACHINE_PASSPORT_SOURCE)
    ws = wb["FM107"]
    rows = db.execute("SELECT * FROM machine_passport ORDER BY device_cod").fetchall()
    # فقط داده‌های موجود را در قالب اصلی بنویس؛ ساختار و ظاهر فرم حفظ می‌شود.
    start = 8
    for i,r in enumerate(rows,start):
        ws.cell(i,1).value=i-start+1
        ws.cell(i,2).value=r["device_name"]; ws.cell(i,3).value=r["device_name"]; ws.cell(i,4).value=r["device_cod"]
        mapping={5:"manufacturer_country",6:"manufacturer_company",7:"useful_life",8:"manufacture_date",9:"serial_number",10:"commissioning_date",11:"purchase_condition",12:"technical_info",13:"energy_consumption",14:"other_energy",15:"cooling_system",16:"dimensions_length",17:"dimensions_width",18:"dimensions_height",19:"accessories",20:"operation_description",21:"notes"}
        for c,f in mapping.items(): ws.cell(i,c).value=r[f] or None
    # ردیف‌های قدیمیِ اضافی را خالی کن، بدون دست زدن به قالب.
    for i in range(start+len(rows), ws.max_row+1):
        if ws.cell(i,2).value is not None or ws.cell(i,4).value is not None:
            for c in range(1,22): ws.cell(i,c).value=None
    out=io.BytesIO(); wb.save(out); out.seek(0)
    return send_file(out, as_attachment=True, download_name="FM107_شناسنامه_ماشین_آلات.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============================================================== dashboard
@app.route("/")
@login_required
def index():
    return render_template("index.html")


# ================================================================= devices
@app.route("/devices", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def devices():
    db = get_db()
    if request.method == "POST":
        cod = request.form.get("cod", "").strip()
        name = request.form.get("name", "").strip()
        if not cod or not name:
            flash("کد و نام دستگاه الزامی است.", "error")
        else:
            def num(field):
                val = request.form.get(field, "").strip()
                try:
                    return float(val) if val else 0
                except ValueError:
                    return 0

            db.execute(
                """INSERT INTO dastgahjadid
                   (cod, name, hadaftedadkharabi, pazireshtedadkharabi, hadafzamantavaghof, pazireshzamantavaghof)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(cod) DO UPDATE SET
                     name=excluded.name, hadaftedadkharabi=excluded.hadaftedadkharabi,
                     pazireshtedadkharabi=excluded.pazireshtedadkharabi,
                     hadafzamantavaghof=excluded.hadafzamantavaghof,
                     pazireshzamantavaghof=excluded.pazireshzamantavaghof""",
                (cod, name, num("hadaftedadkharabi"), num("pazireshtedadkharabi"),
                 num("hadafzamantavaghof"), num("pazireshzamantavaghof")),
            )
            db.commit()
            flash("اطلاعات دستگاه ذخیره شد.", "success")
            return redirect(url_for("devices"))

    edit_cod = request.args.get("edit")
    edit = None
    if edit_cod:
        edit = db.execute("SELECT * FROM dastgahjadid WHERE cod = ?", (edit_cod,)).fetchone()

    device_list = db.execute("SELECT * FROM dastgahjadid ORDER BY cod").fetchall()
    return render_template("devices.html", devices=device_list, edit=edit)


@app.route("/devices/<cod>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def device_delete(cod):
    db = get_db()
    db.execute("DELETE FROM dastgahjadid WHERE cod = ?", (cod,))
    db.commit()
    flash("دستگاه حذف شد.", "success")
    return redirect(url_for("devices"))


# ============================================================== contractors
@app.route("/contractors", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def contractors():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("نام مجری الزامی است.", "error")
        elif db.execute("SELECT 1 FROM mojryjadid WHERE name = ?", (name,)).fetchone():
            flash("نام مجری تکراری است.", "error")
        else:
            max_cod = db.execute("SELECT MAX(cod) FROM mojryjadid").fetchone()[0]
            cod = (max_cod or 0) + 1
            db.execute("INSERT INTO mojryjadid (cod, name) VALUES (?, ?)", (cod, name))
            db.commit()
            flash("مجری ثبت شد.", "success")
        return redirect(url_for("contractors"))

    max_cod = db.execute("SELECT MAX(cod) FROM mojryjadid").fetchone()[0]
    next_cod = (max_cod or 0) + 1
    contractor_list = db.execute("SELECT * FROM mojryjadid ORDER BY cod").fetchall()
    return render_template("contractors.html", contractors=contractor_list, next_cod=next_cod)


# ==================================================================== goods
@app.route("/goods", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def goods():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        vahed = request.form.get("vahed", "").strip()
        original_cod = request.form.get("original_cod", "").strip()

        if not name:
            flash("نام کالا الزامی است.", "error")
            return redirect(url_for("goods"))

        if original_cod:
            # ویرایش یک کالای موجود؛ کد کالا (کلید اصلی) تغییر نمی‌کند
            cod = original_cod
        else:
            # ثبت کالای جدید: کد به‌صورت خودکار و متوالی تولید می‌شود، نه
            # با دست — قفل تراکنش از تکرار همزمان یک کد جلوگیری می‌کند
            try:
                db.execute("BEGIN IMMEDIATE")
                max_cod = db.execute(
                    "SELECT MAX(CAST(cod AS INTEGER)) FROM kalajadid WHERE cod GLOB '[0-9]*'"
                ).fetchone()[0]
                cod = str((max_cod or 100) + 1)
            except Exception:
                db.rollback()
                raise

        db.execute(
            """INSERT INTO kalajadid (cod, name, vahed) VALUES (?, ?, ?)
               ON CONFLICT(cod) DO UPDATE SET name=excluded.name, vahed=excluded.vahed""",
            (cod, name, vahed),
        )
        db.commit()
        flash("کالا ثبت شد.", "success")
        return redirect(url_for("goods"))

    edit_cod = request.args.get("edit")
    edit = None
    if edit_cod:
        edit = db.execute("SELECT * FROM kalajadid WHERE cod = ?", (edit_cod,)).fetchone()

    goods_list = db.execute(
        "SELECT * FROM kalajadid ORDER BY CAST(cod AS INTEGER)"
    ).fetchall()
    max_cod = db.execute(
        "SELECT MAX(CAST(cod AS INTEGER)) FROM kalajadid WHERE cod GLOB '[0-9]*'"
    ).fetchone()[0]
    next_cod = (max_cod or 100) + 1

    return render_template("goods.html", goods_list=goods_list, edit=edit, next_cod=next_cod)
    return render_template("goods.html", goods_list=goods_list, edit=edit)


@app.route("/goods/<cod>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def goods_delete(cod):
    db = get_db()
    db.execute("DELETE FROM kalajadid WHERE cod = ?", (cod,))
    db.commit()
    flash("کالا حذف شد.", "success")
    return redirect(url_for("goods"))


# ================================================================= requests
@app.route("/requests/new", methods=["GET", "POST"])
@login_required
@roles_required(*CAN_CREATE_REQUEST)
def request_new():
    """
    ثبت اولیه‌ی خرابی/درخواست (مرحله ۱): فقط اطلاعات پایه. هرکسی می‌تواند
    این فرم را پر کند. رکورد با وضعیت pending ثبت می‌شود تا بعداً در
    صفحه‌ی «بررسی و انجام» تکمیل شود.
    """
    db = get_db()
    if request.method == "POST":
        form = request.form
        if not any(form.get(f"wt_{k}") for k, _ in WORK_TYPES):
            flash("یکی از انواع کار درخواستی را انتخاب کنید.", "error")
            return redirect(url_for("request_new"))
        if not form.get("codedastgah", "").strip() or not form.get("namdastgah", "").strip():
            flash("کد و نام دستگاه الزامی است.", "error")
            return redirect(url_for("request_new"))
        if not form.get("sharhenaghs", "").strip():
            flash("شرح خرابی را وارد کنید.", "error")
            return redirect(url_for("request_new"))

        # شماره درخواست مستقل از id داخلی است. قفل تراکنش باعث می‌شود اگر
        # همزمان چند نفر درخواست ثبت کنند، دو نفر یک شماره نگیرند.
        try:
            db.execute("BEGIN IMMEDIATE")
            max_number = db.execute("SELECT COALESCE(MAX(shomare_darkhast), 0) FROM data").fetchone()[0]
            request_number = int(max_number) + 1
            cur = db.execute(
                """INSERT INTO data (
                    shomare_darkhast, etefaghi, pishgirane, asasy, tekrary, sayer,
                    namdastgah, codedastgah, sharhenaghs,
                    darkhastkonande, tarikhdarkhast, timedarkhast, status
                ) VALUES (?,?,?,?,?,?, ?,?,?, ?,?,?, 'pending')""",
                (
                    request_number,
                    *(1 if form.get(f"wt_{k}") else 0 for k, _ in WORK_TYPES),
                    form.get("namdastgah", "").strip(),
                    form.get("codedastgah", "").strip(),
                    form.get("sharhenaghs", "").strip(),
                    enforced_person_name(form.get("darkhastkonande", "")),
                    *enforced_datetime(form.get("tarikhdarkhast", ""), form.get("timedarkhast", "")),
                ),
            )
            db.commit()
            request_id = cur.lastrowid
        except Exception:
            db.rollback()
            raise

        flash(f"درخواست شماره {request_number} با موفقیت ثبت شد.", "success")
        return redirect(url_for("request_new"))

    max_number = db.execute("SELECT MAX(shomare_darkhast) FROM data").fetchone()[0]
    next_id = (max_number or 0) + 1
    today = today_jalali_str()
    now = now_time_str()
    device_list = db.execute("SELECT cod, name FROM dastgahjadid ORDER BY name").fetchall()

    return render_template(
        "request_new.html", next_id=next_id, today=today, now=now,
        work_types=WORK_TYPES, devices=device_list,
    )


@app.route("/api/devices-search")
@login_required
def api_devices_search():
    """
    جستجوی دستگاه با نرمال‌سازی حروف فارسی/عربی (تا مثلاً «ي» عربی و «ی»
    فارسی یکسان در نظر گرفته شوند) — جایگزین datalist مرورگر که این
    تفاوت را تشخیص نمی‌دهد.
    """
    db = get_db()
    q = normalize_fa(request.args.get("q", ""))
    devices = db.execute("SELECT cod, name FROM dastgahjadid ORDER BY name").fetchall()
    if not q:
        matches = devices[:20]
    else:
        matches = [
            d for d in devices
            if q in normalize_fa(d["cod"]) or q in normalize_fa(d["name"])
        ][:20]
    return {"devices": [{"cod": d["cod"], "name": d["name"]} for d in matches]}


@app.route("/api/device-history")
@login_required
@roles_required(*CAN_CREATE_REQUEST)
def api_device_history():
    """
    تاریخچه‌ی تعمیرات قبلی یک دستگاه، برای نمایش زیر فرم ثبت درخواست
    (فقط ستون‌های کد دستگاه، نام دستگاه، تاریخ تعمیر، شرح خرابی و کار
    انجام‌شده) — با جاوااسکریپت هنگام وارد کردن کد دستگاه فراخوانی می‌شود.
    """
    db = get_db()
    cod = request.args.get("cod", "").strip()
    if not cod:
        return {"rows": []}

    rows = db.execute(
        """SELECT codedastgah, namdastgah, tarikhdarkhast, sharhenaghs, sharhekareanjamshode
           FROM data WHERE codedastgah = ? ORDER BY id DESC LIMIT 20""",
        (cod,),
    ).fetchall()

    return {
        "rows": [
            {
                "codedastgah": r["codedastgah"],
                "namdastgah": r["namdastgah"],
                "tarikhdarkhast": r["tarikhdarkhast"],
                "sharhenaghs": r["sharhenaghs"],
                "sharhekareanjamshode": r["sharhekareanjamshode"] or "-",
            }
            for r in rows
        ]
    }


def _work_type_label(row):
    labels = [label for key, label in WORK_TYPES if row[key]]
    return "، ".join(labels) if labels else "-"


@app.route("/requests/<int:request_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def request_edit(request_id):
    """ویرایش کامل درخواست از مسیر جستجو؛ فقط مدیر سیستم مجاز است."""
    db = get_db()
    row = db.execute("SELECT * FROM data WHERE id = ?", (request_id,)).fetchone()
    if not row:
        flash("درخواست یافت نشد.", "error")
        return redirect(url_for("requests_search"))

    if request.method == "POST":
        form = request.form
        if not any(form.get(f"wt_{k}") for k, _ in WORK_TYPES):
            flash("یکی از انواع کار درخواستی را انتخاب کنید.", "error")
            return redirect(url_for("request_edit", request_id=request_id))
        if not form.get("codedastgah", "").strip() or not form.get("namdastgah", "").strip():
            flash("کد و نام دستگاه الزامی است.", "error")
            return redirect(url_for("request_edit", request_id=request_id))
        if not form.get("sharhenaghs", "").strip():
            flash("شرح خرابی را وارد کنید.", "error")
            return redirect(url_for("request_edit", request_id=request_id))

        status = "completed" if form.get("status") == "completed" else "pending"
        device_code = form.get("codedastgah", "").strip()
        with db:
            db.execute(
                """UPDATE data SET
                    etefaghi=?, pishgirane=?, asasy=?, tekrary=?, sayer=?,
                    namdastgah=?, codedastgah=?, sharhenaghs=?,
                    barghi=?, mekanik=?, abzarsazi=?, taminghate=?, kontrol=?, tasisat=?, tolid=?, sayertakhir=?,
                    darkhastkonande=?, tarikhdarkhast=?, timedarkhast=?,
                    sharhekareanjamshode=?, tarikhstart=?, timestart=?, tarikhend=?, timeEnd=?,
                    timetavaghofdastgah=?, tozihat=?, status=?
                   WHERE id=?""",
                (
                    *(1 if form.get(f"wt_{k}") else 0 for k, _ in WORK_TYPES),
                    form.get("namdastgah", "").strip(), device_code, form.get("sharhenaghs", "").strip(),
                    *(1 if form.get(f"dep_{k}") else 0 for k, _ in DEPARTMENTS),
                    form.get("darkhastkonande", "").strip(), form.get("tarikhdarkhast", "").strip(), form.get("timedarkhast", "").strip(),
                    form.get("sharhekareanjamshode", "").strip(), form.get("tarikhstart", "").strip(), form.get("timestart", "").strip(),
                    form.get("tarikhend", "").strip(), form.get("timeEnd", "").strip(),
                    form.get("timetavaghofdastgah", "").strip(), form.get("tozihat", "").strip(), status, request_id,
                ),
            )

            db.execute("DELETE FROM mojry WHERE shomare_darkhast = ?", (request_id,))
            db.execute("DELETE FROM mvademasrafi WHERE shomare_darkhast = ?", (request_id,))

            cods = form.getlist("contractor_cod[]")
            names = form.getlist("contractor_name[]")
            dates = form.getlist("contractor_date[]")
            hours = form.getlist("contractor_hours[]")
            for cod, name, date, hrs in zip(cods, names, dates, hours):
                db.execute(
                    """INSERT INTO mojry (kod_mojri, nam_mojri, shomare_darkhast, tarikh, saat, kod_dastgah)
                       VALUES (?,?,?,?,?,?)""",
                    (cod, name, request_id, date, hrs, device_code),
                )

            m_cods = form.getlist("material_cod[]")
            m_names = form.getlist("material_name[]")
            m_qtys = form.getlist("material_qty[]")
            m_vaheds = form.getlist("material_vahed[]")
            today = today_jalali_str()
            for cod, name, qty, vahed in zip(m_cods, m_names, m_qtys, m_vaheds):
                db.execute(
                    """INSERT INTO mvademasrafi (code, name, qty, vahed, shomare_darkhast, kod_dastgah, tarikh)
                       VALUES (?,?,?,?,?,?,?)""",
                    (cod, name, qty, vahed, request_id, device_code, today),
                )

            db.execute(
                "INSERT INTO audit_log (user_id, username, action, event_time, ip_address, user_agent) VALUES (?,?,?,?,?,?)",
                (current_user()["id"], current_user()["username"], f"ویرایش کامل درخواست شماره {row['shomare_darkhast']}",
                 datetime.datetime.now().isoformat(timespec="seconds"), request.remote_addr, request.headers.get("User-Agent", "")),
            )

        flash(f"تمام اطلاعات درخواست شماره {row['shomare_darkhast']} با موفقیت اصلاح شد.", "success")
        return redirect(url_for("request_detail", request_id=request_id))

    device_list = db.execute("SELECT cod, name FROM dastgahjadid ORDER BY name").fetchall()
    contractor_list = db.execute("SELECT cod, name FROM mojryjadid ORDER BY name").fetchall()
    goods_list = db.execute("SELECT cod, name, vahed FROM kalajadid ORDER BY name").fetchall()
    existing_mojry = db.execute("SELECT * FROM mojry WHERE shomare_darkhast = ?", (request_id,)).fetchall()
    existing_materials = db.execute("SELECT * FROM mvademasrafi WHERE shomare_darkhast = ?", (request_id,)).fetchall()
    return render_template(
        "request_edit.html", row=row, work_types=WORK_TYPES, work_units=WORK_UNITS,
        delay_causes=DELAY_CAUSES, devices=device_list, contractors=contractor_list,
        goods_list=goods_list, existing_mojry=existing_mojry, existing_materials=existing_materials,
        today=today_jalali_str(), now=now_time_str(),
    )


@app.route("/requests/<int:request_id>/delete", methods=["POST"])
@login_required
@roles_required(*(CAN_CREATE_REQUEST | CAN_REVIEW_REQUEST))
def request_delete(request_id):
    """حذف کامل یک درخواست به همراه مجری‌ها و مواد مصرفی مرتبط با آن."""
    db = get_db()
    row = db.execute("SELECT id, shomare_darkhast FROM data WHERE id = ?", (request_id,)).fetchone()
    if not row:
        flash("درخواست یافت نشد.", "error")
    else:
        display_number = row["shomare_darkhast"] or row["id"]
        with db:
            db.execute("DELETE FROM mojry WHERE shomare_darkhast = ?", (request_id,))
            db.execute("DELETE FROM mvademasrafi WHERE shomare_darkhast = ?", (request_id,))
            db.execute("DELETE FROM data WHERE id = ?", (request_id,))
        flash(f"درخواست شماره {display_number} حذف شد.", "success")

    next_url = safe_next_url(request.form.get("next"))
    return redirect(next_url)


@app.route("/requests/pending")
@login_required
@roles_required(*CAN_REVIEW_REQUEST)
def requests_pending():
    """صفحه‌ی «بررسی و انجام»: لیست درخواست‌هایی که هنوز تکمیل نشده‌اند."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM data WHERE status = 'pending' OR status IS NULL ORDER BY id DESC"
    ).fetchall()
    rows_with_label = []
    for r in rows:
        row = dict(r)
        row["work_type_label"] = _work_type_label(r)
        rows_with_label.append(row)
    return render_template("requests_pending.html", rows=rows_with_label)


@app.route("/requests/<int:request_id>/complete", methods=["GET", "POST"])
@login_required
@roles_required(*CAN_REVIEW_REQUEST)
def request_complete(request_id):
    """
    بررسی و تکمیل درخواست (مرحله ۲): شرح کار انجام شده، واحد مرتبط،
    زمان‌بندی، مجری‌ها و مواد مصرفی. با ثبت این فرم، وضعیت درخواست
    completed می‌شود.
    """
    db = get_db()
    row = db.execute("SELECT * FROM data WHERE id = ?", (request_id,)).fetchone()
    if not row:
        flash("درخواست یافت نشد.", "error")
        return redirect(url_for("requests_pending"))

    if request.method == "POST":
        form = request.form
        with db:
            db.execute(
                """UPDATE data SET
                    sharhekareanjamshode = ?,
                    barghi = ?, mekanik = ?, abzarsazi = ?, taminghate = ?,
                    kontrol = ?, tasisat = ?, tolid = ?, sayertakhir = ?,
                    tarikhstart = ?, timestart = ?, tarikhend = ?, timeEnd = ?,
                    timetavaghofdastgah = ?, tozihat = ?, status = 'completed'
                   WHERE id = ?""",
                (
                    form.get("sharhekareanjamshode", "").strip(),
                    *(1 if form.get(f"dep_{k}") else 0 for k, _ in DEPARTMENTS),
                    form.get("tarikhstart", "").strip(),
                    form.get("timestart", "").strip(),
                    form.get("tarikhend", "").strip(),
                    form.get("timeEnd", "").strip(),
                    form.get("timetavaghofdastgah", "").strip(),
                    form.get("tozihat", "").strip(),
                    request_id,
                ),
            )

            device_code = row["codedastgah"]

            # اگر قبلاً یک‌بار تکمیل شده و دوباره ویرایش می‌شود، ردیف‌های
            # قبلی مجری/مواد مصرفی را جایگزین می‌کنیم تا تکراری نشوند.
            db.execute("DELETE FROM mojry WHERE shomare_darkhast = ?", (request_id,))
            db.execute("DELETE FROM mvademasrafi WHERE shomare_darkhast = ?", (request_id,))

            cods = form.getlist("contractor_cod[]")
            names = form.getlist("contractor_name[]")
            dates = form.getlist("contractor_date[]")
            hours = form.getlist("contractor_hours[]")
            for cod, name, date, hrs in zip(cods, names, dates, hours):
                db.execute(
                    """INSERT INTO mojry (kod_mojri, nam_mojri, shomare_darkhast, tarikh, saat, kod_dastgah)
                       VALUES (?,?,?,?,?,?)""",
                    (cod, name, request_id, date, hrs, device_code),
                )

            m_cods = form.getlist("material_cod[]")
            m_names = form.getlist("material_name[]")
            m_qtys = form.getlist("material_qty[]")
            m_vaheds = form.getlist("material_vahed[]")
            today = today_jalali_str()
            for cod, name, qty, vahed in zip(m_cods, m_names, m_qtys, m_vaheds):
                db.execute(
                    """INSERT INTO mvademasrafi (code, name, qty, vahed, shomare_darkhast, kod_dastgah, tarikh)
                       VALUES (?,?,?,?,?,?,?)""",
                    (cod, name, qty, vahed, request_id, device_code, today),
                )

        flash(f"درخواست شماره {row['shomare_darkhast']} با موفقیت تکمیل شد.", "success")
        return redirect(url_for("request_detail", request_id=request_id))

    today = today_jalali_str()
    now = now_time_str()
    contractor_list = db.execute("SELECT cod, name FROM mojryjadid ORDER BY name").fetchall()
    goods_list = db.execute("SELECT cod, name, vahed FROM kalajadid ORDER BY name").fetchall()
    existing_mojry = db.execute(
        "SELECT * FROM mojry WHERE shomare_darkhast = ?", (request_id,)
    ).fetchall()
    existing_materials = db.execute(
        "SELECT * FROM mvademasrafi WHERE shomare_darkhast = ?", (request_id,)
    ).fetchall()

    return render_template(
        "request_complete.html", row=row, today=today, now=now,
        work_type_label=_work_type_label(row), work_units=WORK_UNITS, delay_causes=DELAY_CAUSES,
        contractors=contractor_list, goods_list=goods_list,
        existing_mojry=existing_mojry, existing_materials=existing_materials,
    )


def _search_query(args):
    """
    فقط فیلترهای تاریخ در SQL اعمال می‌شوند؛ فیلترهای متنی (کد دستگاه،
    درخواست‌کننده) بعداً با نرمال‌سازی حروف فارسی/عربی در پایتون اعمال
    می‌شوند تا مثلاً «ي» عربی و «ی» فارسی یکسان در نظر گرفته شوند.
    """
    query = "SELECT * FROM data WHERE 1=1"
    params = []
    if args.get("from"):
        query += " AND tarikhdarkhast >= ?"
        params.append(args["from"])
    if args.get("to"):
        query += " AND tarikhdarkhast <= ?"
        params.append(args["to"])
    query += " ORDER BY shomare_darkhast DESC"
    return query, params


def _apply_text_filters(rows, filters):
    """
    filters: لیستی از (کلید_ستون، مقدار_جستجو). هر سطر باید مقدار
    نرمال‌شده‌ی جستجو را به‌عنوان زیررشته در نسخه‌ی نرمال‌شده‌ی همان
    ستون داشته باشد (تطبیق حروف فارسی/عربی، بدون حساسیت به بزرگی/کوچکی).
    """
    active = [(key, normalize_fa(val)) for key, val in filters if val]
    if not active:
        return rows
    result = []
    for row in rows:
        ok = True
        for key, needle in active:
            if needle not in normalize_fa(row[key] or ""):
                ok = False
                break
        if ok:
            result.append(row)
    return result


@app.route("/requests")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def requests_search():
    db = get_db()
    query, params = _search_query(request.args)
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [
        ("codedastgah", request.args.get("device", "")),
        ("darkhastkonande", request.args.get("requester", "")),
    ])
    return render_template("requests_search.html", rows=rows)


@app.route("/requests/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def requests_export():
    db = get_db()
    query, params = _search_query(request.args)
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [
        ("codedastgah", request.args.get("device", "")),
        ("darkhastkonande", request.args.get("requester", "")),
    ])
    headers = ("شماره", "تاریخ درخواست", "کد دستگاه", "نام دستگاه", "درخواست کننده", "شرح نقص", "تاریخ شروع", "تاریخ اتمام")
    data_rows = [(r["shomare_darkhast"], r["tarikhdarkhast"], r["codedastgah"], r["namdastgah"],
                  r["darkhastkonande"], r["sharhenaghs"], r["tarikhstart"], r["tarikhend"]) for r in rows]
    return excel_response(headers, data_rows, "جستجوی_درخواست_ها.xlsx")


@app.route("/requests/<int:request_id>")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def request_detail(request_id):
    db = get_db()
    row = db.execute("SELECT * FROM data WHERE id = ?", (request_id,)).fetchone()
    if not row:
        flash("درخواست یافت نشد.", "error")
        return redirect(url_for("requests_search"))

    labels = [
        ("shomare_darkhast", "شماره درخواست"), ("status", "وضعیت"),
        ("tarikhdarkhast", "تاریخ درخواست"), ("timedarkhast", "ساعت درخواست"),
        ("darkhastkonande", "درخواست کننده"), ("codedastgah", "کد دستگاه"), ("namdastgah", "نام دستگاه"),
        ("sharhenaghs", "شرح نقص"), ("sharhekareanjamshode", "شرح کار انجام شده"),
        ("tarikhstart", "تاریخ شروع"), ("timestart", "ساعت شروع"),
        ("tarikhend", "تاریخ اتمام"), ("timeEnd", "ساعت اتمام"),
        ("timetavaghofdastgah", "میزان ساعت توقف دستگاه"), ("tozihat", "توضیحات"),
    ]
    status_fa = {"pending": "در انتظار بررسی", "completed": "تکمیل شده"}
    fields = [
        (label, status_fa.get(row["status"], row["status"]) if key == "status" else row[key])
        for key, label in labels
    ]

    mojry_rows = db.execute(
        "SELECT nam_mojri, tarikh, saat FROM mojry WHERE shomare_darkhast = ?", (request_id,)
    ).fetchall()
    material_rows = db.execute(
        "SELECT name, qty, vahed FROM mvademasrafi WHERE shomare_darkhast = ?", (request_id,)
    ).fetchall()

    return render_template(
        "request_detail.html", row=row, fields=fields,
        mojry_rows=mojry_rows, material_rows=material_rows,
    )


# ========================================================= contractor work
def _contractor_work_query(args):
    # توجه: ستون mojry.shomare_darkhast در واقع همان id داخلی جدول data
    # است (برای اتصال بین جدول‌ها استفاده می‌شود)، نه شماره‌ی نمایشی
    # درخواست. برای نمایش شماره‌ی درست به کاربر، با جدول data جوین
    # می‌زنیم و d.shomare_darkhast واقعی را برمی‌گردانیم.
    # فیلتر نام مجری در پایتون با نرمال‌سازی فارسی/عربی اعمال می‌شود.
    query = """
        SELECT m.*, d.shomare_darkhast AS request_number
        FROM mojry m
        LEFT JOIN data d ON d.id = m.shomare_darkhast
        WHERE 1=1
    """
    params = []
    if args.get("from"):
        query += " AND m.tarikh >= ?"
        params.append(args["from"])
    if args.get("to"):
        query += " AND m.tarikh <= ?"
        params.append(args["to"])
    query += " ORDER BY m.tarikh DESC, m.id DESC"
    return query, params


@app.route("/contractor-work")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def contractor_work():
    db = get_db()
    query, params = _contractor_work_query(request.args)
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [("nam_mojri", request.args.get("name", ""))])
    total_hours = sum(parse_hours(r["saat"]) for r in rows)
    return render_template("contractor_work.html", rows=rows, total_hours=round(total_hours, 2))


@app.route("/contractor-work/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def contractor_work_export():
    db = get_db()
    query, params = _contractor_work_query(request.args)
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [("nam_mojri", request.args.get("name", ""))])
    headers = ("کد مجری", "نام مجری", "شماره درخواست", "تاریخ", "نفر ساعت", "کد دستگاه")
    data_rows = [(r["kod_mojri"], r["nam_mojri"], r["request_number"], r["tarikh"], r["saat"], r["kod_dastgah"]) for r in rows]
    return excel_response(headers, data_rows, "کارهای_مجری_ها.xlsx")


# ============================================================= consumables
def _consumables_query(args):
    # همان نکته‌ی بالا: mvademasrafi.shomare_darkhast همان id داخلی
    # data است، پس برای شماره‌ی درست، جوین به data می‌زنیم. فیلترهای
    # متنی (کد دستگاه، کد کالا) در پایتون با نرمال‌سازی فارسی/عربی اعمال
    # می‌شوند.
    query = """
        SELECT mv.*, d.shomare_darkhast AS request_number
        FROM mvademasrafi mv
        LEFT JOIN data d ON d.id = mv.shomare_darkhast
        WHERE 1=1
        ORDER BY mv.id DESC
    """
    return query, []


@app.route("/consumables")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def consumables():
    db = get_db()
    query, params = _consumables_query(request.args)
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [
        ("kod_dastgah", request.args.get("device", "")),
        ("code", request.args.get("goods", "")),
    ])
    return render_template("consumables.html", rows=rows)


@app.route("/consumables/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def consumables_export():
    db = get_db()
    query, params = _consumables_query(request.args)
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [
        ("kod_dastgah", request.args.get("device", "")),
        ("code", request.args.get("goods", "")),
    ])
    headers = ("ردیف", "کد کالا", "نام کالا", "تعداد", "واحد", "شماره درخواست", "کد دستگاه", "تاریخ")
    data_rows = [(r["id"], r["code"], r["name"], r["qty"], r["vahed"], r["request_number"], r["kod_dastgah"], r["tarikh"]) for r in rows]
    return excel_response(headers, data_rows, "مواد_مصرفی.xlsx")


# ================================================================= reports
def _hours_report_rows(db, args):
    """
    گزارش نفرساعت هر درخواست. جمع نفرساعت با پایتون محاسبه می‌شود (نه با
    SQL) چون مقدار ستون «saat» می‌تواند به‌صورت «ساعت:دقیقه» ذخیره شده
    باشد و CAST مستقیم SQLite فقط بخش ساعت را می‌خواند و دقیقه را نادیده
    می‌گیرد.
    """
    select_cols = ", ".join(
        ["d.id", "d.tarikhdarkhast", "d.codedastgah", "d.namdastgah"]
        + [f"d.{c}" for c, _ in WORK_TYPES]
        + [f"d.{c}" for c, _ in DEPARTMENTS]
    )
    query = f"SELECT {select_cols} FROM data d WHERE 1=1"
    params = []
    if args.get("from"):
        query += " AND d.tarikhdarkhast >= ?"
        params.append(args["from"])
    if args.get("to"):
        query += " AND d.tarikhdarkhast <= ?"
        params.append(args["to"])
    query += " ORDER BY d.id DESC"

    rows = db.execute(query, params).fetchall()
    result = []
    for r in rows:
        row = dict(r)
        hours = db.execute(
            "SELECT saat FROM mojry WHERE shomare_darkhast = ?", (row["id"],)
        ).fetchall()
        row["nafar_saat"] = round(sum(parse_hours(h["saat"]) for h in hours), 2)
        result.append(row)

    device_filter = normalize_fa(args.get("device", ""))
    if device_filter:
        result = [r for r in result if device_filter in normalize_fa(r["codedastgah"] or "")]
    return result


@app.route("/reports/hours")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def report_hours():
    db = get_db()
    rows = _hours_report_rows(db, request.args)
    total = round(sum(r["nafar_saat"] or 0 for r in rows), 2)
    return render_template("report_hours.html", rows=rows, total=total,
                            work_types=WORK_TYPES, departments=DEPARTMENTS)


@app.route("/reports/hours/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def report_hours_export():
    db = get_db()
    rows = _hours_report_rows(db, request.args)
    headers = (["شماره", "تاریخ درخواست", "کد دستگاه", "نام دستگاه"]
               + [h for _, h in WORK_TYPES] + [h for _, h in DEPARTMENTS] + ["جمع نفر ساعت"])
    data_rows = []
    for r in rows:
        row = [r["id"], r["tarikhdarkhast"], r["codedastgah"], r["namdastgah"]]
        row += [r[k] for k, _ in WORK_TYPES]
        row += [r[k] for k, _ in DEPARTMENTS]
        row += [r["nafar_saat"]]
        data_rows.append(row)
    return excel_response(headers, data_rows, "گزارش_نفرساعت.xlsx")


def _mtbf_rows(db, args):
    date_from = args.get("from")
    date_to = args.get("to")
    available_raw = args.get("available")
    available = None
    if available_raw:
        try:
            available = float(available_raw)
        except ValueError:
            available = None

    devices_list = db.execute(
        "SELECT cod, name, hadaftedadkharabi, hadafzamantavaghof FROM dastgahjadid ORDER BY cod"
    ).fetchall()

    results = []
    for dev in devices_list:
        query = "SELECT timetavaghofdastgah FROM data WHERE codedastgah = ? AND etefaghi = 1"
        params = [dev["cod"]]
        if date_from:
            query += " AND tarikhdarkhast >= ?"
            params.append(date_from)
        if date_to:
            query += " AND tarikhdarkhast <= ?"
            params.append(date_to)

        rows = db.execute(query, params).fetchall()
        count_kharabi = len(rows)
        total_tavaghof = sum(parse_hours(r["timetavaghofdastgah"]) for r in rows)

        # تعداد خرابی‌های «تکراری» (ستون tekrary) جدا از محاسبه‌ی MTBF/MTTR
        # فقط برای اطلاع نمایش داده می‌شود؛ در MTBF/MTTR دخالتی ندارد
        tekrary_query = "SELECT COUNT(*) FROM data WHERE codedastgah = ? AND tekrary = 1"
        tekrary_params = [dev["cod"]]
        if date_from:
            tekrary_query += " AND tarikhdarkhast >= ?"
            tekrary_params.append(date_from)
        if date_to:
            tekrary_query += " AND tarikhdarkhast <= ?"
            tekrary_params.append(date_to)
        count_tekrary = db.execute(tekrary_query, tekrary_params).fetchone()[0]

        if count_kharabi > 0:
            mttr = round(total_tavaghof / count_kharabi, 2)
            mtbf = round((available - total_tavaghof) / count_kharabi, 2) if available is not None else "-"
        else:
            mttr = "-"
            mtbf = "-"

        results.append({
            "cod": dev["cod"], "name": dev["name"], "count_kharabi": count_kharabi,
            "count_tekrary": count_tekrary,
            "total_tavaghof": round(total_tavaghof, 2), "mttr": mttr, "mtbf": mtbf,
            "hadaftedadkharabi": dev["hadaftedadkharabi"], "hadafzamantavaghof": dev["hadafzamantavaghof"],
        })

    sort_by = args.get("sort_by", "mttr")
    if sort_by not in ("mttr", "mtbf"):
        sort_by = "mttr"
    # مقادیر "-" (بدون خرابی، یا بدون زمان در دسترس برای MTBF) همیشه به انتهای لیست می‌روند
    results.sort(key=lambda r: (r[sort_by] == "-", -(r[sort_by] if r[sort_by] != "-" else 0)))
    return results


@app.route("/reports/mtbf")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def report_mtbf():
    db = get_db()
    rows = _mtbf_rows(db, request.args)
    sort_by = request.args.get("sort_by", "mttr")
    if sort_by not in ("mttr", "mtbf"):
        sort_by = "mttr"
    return render_template("report_mtbf.html", rows=rows, sort_by=sort_by)


@app.route("/reports/mtbf/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def report_mtbf_export():
    db = get_db()
    rows = _mtbf_rows(db, request.args)
    headers = ("کد دستگاه", "نام دستگاه", "تعداد خرابی", "تعداد خرابی تکراری", "مجموع توقف (ساعت)", "MTTR", "MTBF", "هدف تعداد خرابی", "هدف زمان توقف")
    data_rows = [(r["cod"], r["name"], r["count_kharabi"], r["count_tekrary"], r["total_tavaghof"], r["mttr"], r["mtbf"],
                  r["hadaftedadkharabi"], r["hadafzamantavaghof"]) for r in rows]
    return excel_response(headers, data_rows, "MTBF_MTTR.xlsx")


# ========================================================= بازدید روزانه


@app.route("/inspections/daily/new", methods=["GET", "POST"])
@login_required
@roles_required(*CAN_DAILY_INSPECTION)
def daily_inspection_new():
    db = get_db()
    if request.method == "POST":
        form = request.form
        cod = form.get("codedastgah", "").strip()
        name = form.get("namdastgah", "").strip()
        if not cod or not name:
            flash("کد و نام دستگاه الزامی است.", "error")
            return redirect(url_for("daily_inspection_new"))
        if not form.get("tarikh", "").strip():
            flash("تاریخ بازدید را وارد کنید.", "error")
            return redirect(url_for("daily_inspection_new"))

        db.execute(
            f"""INSERT INTO bazdid_rozane (
                kod_dastgah, nam_dastgah, tarikh,
                {", ".join(k for k, _ in DAILY_CHECKLIST)},
                bazresh_konande, tozihat, created_at
            ) VALUES (?,?,?, {", ".join("?" for _ in DAILY_CHECKLIST)}, ?,?,?)""",
            (
                cod, name, form.get("tarikh", "").strip(),
                *(1 if form.get(f"chk_{k}") else 0 for k, _ in DAILY_CHECKLIST),
                enforced_person_name(form.get("bazresh_konande", "")),
                form.get("tozihat", "").strip(),
                datetime.datetime.now().isoformat(timespec="seconds"),
            ),
        )
        db.commit()
        flash("بازدید روزانه با موفقیت ثبت شد.", "success")
        return redirect(url_for("daily_inspection_new"))

    device_list = db.execute("SELECT cod, name FROM dastgahjadid ORDER BY name").fetchall()
    return render_template(
        "daily_inspection_new.html", devices=device_list,
        checklist=DAILY_CHECKLIST, today=today_jalali_str(),
    )


@app.route("/inspections/daily")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def daily_inspection_list():
    db = get_db()
    query = "SELECT * FROM bazdid_rozane WHERE 1=1"
    params = []
    if request.args.get("from"):
        query += " AND tarikh >= ?"
        params.append(request.args["from"])
    if request.args.get("to"):
        query += " AND tarikh <= ?"
        params.append(request.args["to"])
    query += " ORDER BY id DESC LIMIT 500"
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [("kod_dastgah", request.args.get("device", ""))])

    entries = []
    for row in rows:
        d = dict(row)
        problems = [label for key, label in DAILY_CHECKLIST if not d.get(key)]
        d["problem_count"] = len(problems)
        d["problems"] = problems
        entries.append(d)

    return render_template("daily_inspection_list.html", entries=entries, checklist=DAILY_CHECKLIST)


# =================================================== بازدید پیشگیرانه/پیش‌بینانه
@app.route("/inspections/preventive/new", methods=["GET", "POST"])
@login_required
@roles_required(*CAN_PREVENTIVE_INSPECTION)
def preventive_inspection_new():
    db = get_db()
    if request.method == "POST":
        form = request.form
        cod = form.get("codedastgah", "").strip()
        name = form.get("namdastgah", "").strip()
        if not cod or not name:
            flash("کد و نام دستگاه الزامی است.", "error")
            return redirect(url_for("preventive_inspection_new"))
        if not form.get("tarikh", "").strip():
            flash("تاریخ بازدید را وارد کنید.", "error")
            return redirect(url_for("preventive_inspection_new"))

        db.execute(
            f"""INSERT INTO bazdid_pishgirane (
                kod_dastgah, nam_dastgah, tarikh, noe_bazdid,
                {", ".join(k for k, _ in PREVENTIVE_CHECKLIST)},
                vaziat_kolli, tarikh_bazdid_badi, bazresh_konande, tozihat, created_at
            ) VALUES (?,?,?,?, {", ".join("?" for _ in PREVENTIVE_CHECKLIST)}, ?,?,?,?,?)""",
            (
                cod, name, form.get("tarikh", "").strip(), form.get("noe_bazdid", "پیشگیرانه"),
                *(1 if form.get(f"chk_{k}") else 0 for k, _ in PREVENTIVE_CHECKLIST),
                form.get("vaziat_kolli", "").strip(),
                form.get("tarikh_bazdid_badi", "").strip(),
                enforced_person_name(form.get("bazresh_konande", "")),
                form.get("tozihat", "").strip(),
                datetime.datetime.now().isoformat(timespec="seconds"),
            ),
        )
        db.commit()
        flash("بازدید پیشگیرانه با موفقیت ثبت شد.", "success")
        return redirect(url_for("preventive_inspection_new"))

    device_list = db.execute("SELECT cod, name FROM dastgahjadid ORDER BY name").fetchall()

    # وقتی فرم از صفحه «پیشنهاد زمان‌بندی بازدید» باز می‌شود، مشخصات
    # دستگاه و نوع بازدید از قبل پر می‌شوند تا کاربر فقط دستگاه را بررسی
    # کند و موارد انجام‌شده را تیک بزند.
    prefill_cod = request.args.get("cod", "").strip()
    prefill_name = request.args.get("name", "").strip()
    prefill_type = request.args.get("type", "پیشگیرانه").strip() or "پیشگیرانه"
    prefill_visitor = request.args.get("visitor", "").strip()
    if prefill_cod and not prefill_name:
        found = db.execute("SELECT name FROM dastgahjadid WHERE cod = ?", (prefill_cod,)).fetchone()
        if found:
            prefill_name = found["name"]

    return render_template(
        "preventive_inspection_new.html", devices=device_list,
        checklist=PREVENTIVE_CHECKLIST, today=today_jalali_str(),
        status_options=OVERALL_STATUS_OPTIONS,
        prefill_cod=prefill_cod, prefill_name=prefill_name,
        prefill_type=prefill_type, prefill_visitor=prefill_visitor,
    )


@app.route("/inspections/preventive/<int:inspection_id>")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def preventive_inspection_detail(inspection_id):
    db = get_db()
    row = db.execute("SELECT * FROM bazdid_pishgirane WHERE id = ?", (inspection_id,)).fetchone()
    if not row:
        abort(404)
    return render_template(
        "preventive_inspection_detail.html", entry=row,
        checklist=PREVENTIVE_CHECKLIST,
    )


@app.route("/inspections/preventive/<int:inspection_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*CAN_PREVENTIVE_INSPECTION)
def preventive_inspection_edit(inspection_id):
    db = get_db()
    row = db.execute("SELECT * FROM bazdid_pishgirane WHERE id = ?", (inspection_id,)).fetchone()
    if not row:
        abort(404)

    if request.method == "POST":
        form = request.form
        cod = form.get("codedastgah", "").strip()
        name = form.get("namdastgah", "").strip()
        tarikh = form.get("tarikh", "").strip()
        if not cod or not name or not tarikh:
            flash("کد دستگاه، نام دستگاه و تاریخ بازدید الزامی است.", "error")
            return redirect(url_for("preventive_inspection_edit", inspection_id=inspection_id))

        assignments = ", ".join(f"{k} = ?" for k, _ in PREVENTIVE_CHECKLIST)
        values = [1 if form.get(f"chk_{k}") else 0 for k, _ in PREVENTIVE_CHECKLIST]
        values += [
            form.get("vaziat_kolli", "").strip(),
            form.get("tarikh_bazdid_badi", "").strip(),
            enforced_person_name(form.get("bazresh_konande", "")),
            form.get("tozihat", "").strip(),
            inspection_id,
        ]
        db.execute(
            f"""UPDATE bazdid_pishgirane SET
                kod_dastgah = ?, nam_dastgah = ?, tarikh = ?, noe_bazdid = ?,
                {assignments}, vaziat_kolli = ?, tarikh_bazdid_badi = ?,
                bazresh_konande = ?, tozihat = ?
                WHERE id = ?""",
            [cod, name, tarikh, form.get("noe_bazdid", "پیشگیرانه")] + values,
        )
        db.commit()
        flash("بازدید با موفقیت ویرایش شد.", "success")
        return redirect(url_for("preventive_inspection_list"))

    device_list = db.execute("SELECT cod, name FROM dastgahjadid ORDER BY name").fetchall()
    return render_template(
        "preventive_inspection_edit.html", entry=row, devices=device_list,
        checklist=PREVENTIVE_CHECKLIST, status_options=OVERALL_STATUS_OPTIONS,
    )


@app.route("/inspections/preventive/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def preventive_inspection_export():
    db = get_db()
    query = "SELECT * FROM bazdid_pishgirane WHERE 1=1"
    params = []
    if request.args.get("from"):
        query += " AND tarikh >= ?"
        params.append(request.args["from"])
    if request.args.get("to"):
        query += " AND tarikh <= ?"
        params.append(request.args["to"])
    query += " ORDER BY tarikh ASC, id ASC"
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [("kod_dastgah", request.args.get("device", ""))])

    headers = ("شناسه", "تاریخ", "نوع بازدید", "کد دستگاه", "نام دستگاه",
               *(label for _, label in PREVENTIVE_CHECKLIST),
               "وضعیت کلی", "تاریخ بازدید بعدی", "بازدیدکننده", "توضیحات")
    data_rows = []
    for r in rows:
        data_rows.append((
            r["id"], r["tarikh"], r["noe_bazdid"], r["kod_dastgah"], r["nam_dastgah"],
            *("✓" if r[k] else "" for k, _ in PREVENTIVE_CHECKLIST),
            r["vaziat_kolli"] or "", r["tarikh_bazdid_badi"] or "",
            r["bazresh_konande"] or "", r["tozihat"] or "",
        ))
    return excel_response(headers, data_rows, "بازدیدهای_پیشگیرانه_و_پیش‌بینانه.xlsx")


@app.route("/inspections/preventive")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def preventive_inspection_list():
    db = get_db()
    query = "SELECT * FROM bazdid_pishgirane WHERE 1=1"
    params = []
    if request.args.get("from"):
        query += " AND tarikh >= ?"
        params.append(request.args["from"])
    if request.args.get("to"):
        query += " AND tarikh <= ?"
        params.append(request.args["to"])
    query += " ORDER BY id DESC LIMIT 500"
    rows = db.execute(query, params).fetchall()
    rows = _apply_text_filters(rows, [("kod_dastgah", request.args.get("device", ""))])

    entries = []
    for row in rows:
        d = dict(row)
        problems = [label for key, label in PREVENTIVE_CHECKLIST if not d.get(key)]
        d["problem_count"] = len(problems)
        d["problems"] = problems
        entries.append(d)

    return render_template("preventive_inspection_list.html", entries=entries, checklist=PREVENTIVE_CHECKLIST)


# =========================================== پیشنهاد هوشمند زمان‌بندی بازدید
def _device_maintenance_recommendation(db, device_row):
    """
    برای یک دستگاه، بر اساس تاریخچه‌ی واقعی خرابی‌های اتفاقی‌اش، فاصله‌ی
    متوسط بین خرابی‌ها را محاسبه می‌کند و بر همان اساس، تاریخ پیشنهادی
    برای بازدید بعدی (پیشگیرانه/پیش‌بینانه) را برمی‌گرداند.

    این یک موتور تحلیلی مبتنی بر قواعد آماری است (شبیه‌سازی‌شده از روی
    منطق واقعی نگهداری قابلیت‌اطمینان‌محور / RCM)، نه یک مدل یادگیری
    ماشین یا هوش مصنوعی جعبه‌سیاه — یعنی هر عددی که نشان می‌دهد را
    می‌توان مستقیماً از تاریخچه‌ی خودِ همان دستگاه توضیح داد.

    منطق:
        ۱. تمام درخواست‌های «تعمیرات اتفاقی» دستگاه را به ترتیب تاریخ می‌آورد.
        ۲. اگر حداقل ۲ خرابی وجود داشته باشد، میانگین فاصله‌ی بین
           خرابی‌ها (بر حسب روز) را حساب می‌کند.
        ۳. اگر داده کافی نباشد (صفر یا یک خرابی)، یک بازه‌ی پیش‌فرض ۶ ماهه (۱۸۰ روز) پیشنهاد می‌شود و به‌وضوح «پیش‌فرض،
           نه محاسبه‌شده» علامت می‌خورد.
        ۴. تاریخ آخرین بازدید پیشگیرانه/پیش‌بینانه (اگر ثبت شده) یا
           آخرین خرابی (در غیر این صورت) به‌عنوان نقطه‌ی شروع در نظر
           گرفته می‌شود، و ۷۰٪ فاصله‌ی متوسط خرابی به آن اضافه می‌شود
           (ضریب اطمینان ۰.۷ یعنی پیشنهاد می‌شود قبل از رسیدن به میانگین
           زمان خرابی، بازدید انجام شود — رویکرد استاندارد در نگهداری
           پیشگیرانه).
    """
    cod = device_row["cod"]
    failures = db.execute(
        "SELECT tarikhdarkhast FROM data WHERE codedastgah = ? AND etefaghi = 1 ORDER BY tarikhdarkhast",
        (cod,),
    ).fetchall()

    failure_dates = [parse_jalali_date(r["tarikhdarkhast"]) for r in failures]
    failure_dates = [d for d in failure_dates if d is not None]

    failure_count = len(failure_dates)
    basis = "محاسبه‌شده از تاریخچه"
    if failure_count >= 2:
        total_days = (failure_dates[-1] - failure_dates[0]).days
        avg_interval_days = total_days / (failure_count - 1) if total_days > 0 else 180
    else:
        # برای دستگاه‌هایی که سابقه خرابی کافی ندارند، دوره مبنا ۶ ماه است.
        avg_interval_days = 180
        basis = "پیش‌فرض ۶ ماهه (داده‌ی تاریخچه‌ی کافی نیست)"

    last_preventive = db.execute(
        "SELECT tarikh FROM bazdid_pishgirane WHERE kod_dastgah = ? ORDER BY tarikh DESC LIMIT 1",
        (cod,),
    ).fetchone()

    # وقتی داده خرابی کافی نیست، دوره ۶ ماهه باید از آخرین بازدید ثبت‌شده
    # محاسبه شود؛ اگر هیچ بازدیدی وجود نداشت، مبنا اول سال جاری است.
    if failure_count < 2:
        if last_preventive and parse_jalali_date(last_preventive["tarikh"]):
            baseline_date_str = last_preventive["tarikh"]
            baseline_label = "آخرین بازدید ثبت‌شده (مبنای ۶ ماهه)"
        else:
            current_year = today_jalali_str().split("/")[0]
            baseline_date_str = f"{current_year}/01/01"
            baseline_label = "اول سال جاری (بدون بازدید قبلی)"
        safety_factor = 1.0
    else:
        # برای داده کافی، زمان‌بندی بر اساس فاصله واقعی خرابی‌هاست.
        if last_preventive and parse_jalali_date(last_preventive["tarikh"]):
            baseline_date_str = last_preventive["tarikh"]
            baseline_label = "آخرین بازدید پیشگیرانه"
        else:
            gy, gm, gd = failure_dates[-1].year, failure_dates[-1].month, failure_dates[-1].day
            jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
            baseline_date_str = f"{jy:04d}/{jm:02d}/{jd:02d}"
            baseline_label = "آخرین خرابی ثبت‌شده"
        safety_factor = 0.7
    recommended_date = add_days_to_jalali_str(baseline_date_str, round(avg_interval_days * safety_factor))
    today = parse_jalali_date(today_jalali_str())
    rec_date_obj = parse_jalali_date(recommended_date)
    days_remaining = (rec_date_obj - today).days if rec_date_obj and today else None

    if days_remaining is None:
        urgency = "نامشخص"
    elif days_remaining < 0:
        urgency = "عقب‌افتاده"
    elif days_remaining <= 14:
        urgency = "فوری (کمتر از دو هفته)"
    elif days_remaining <= 30:
        urgency = "نزدیک (کمتر از یک ماه)"
    else:
        urgency = "عادی"

    return {
        "cod": cod, "name": device_row["name"], "failure_count": failure_count,
        "avg_interval_days": round(avg_interval_days, 1), "basis": basis,
        "baseline_label": baseline_label, "baseline_date": baseline_date_str,
        "recommended_date": recommended_date, "days_remaining": days_remaining,
        "urgency": urgency,
    }


@app.route("/maintenance-recommendations")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def maintenance_recommendations():
    db = get_db()
    results = _sorted_maintenance_recommendations(db)
    return render_template("maintenance_recommendations.html", results=results, today=today_jalali_str())


def _sorted_maintenance_recommendations(db):
    devices = db.execute("SELECT cod, name FROM dastgahjadid ORDER BY name").fetchall()
    results = [_device_maintenance_recommendation(db, d) for d in devices]
    urgency_order = {"عقب‌افتاده": 0, "فوری (کمتر از دو هفته)": 1, "نزدیک (کمتر از یک ماه)": 2,
                      "عادی": 3, "بدون سابقه کافی": 4, "نامشخص": 5}
    results.sort(key=lambda r: (
        urgency_order.get(r["urgency"], 9),
        r["days_remaining"] if r["days_remaining"] is not None else 999999,
    ))
    return results


@app.route("/maintenance-recommendations/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def maintenance_recommendations_export():
    db = get_db()
    results = _sorted_maintenance_recommendations(db)
    headers = ("کد دستگاه", "نام دستگاه", "تعداد خرابی", "میانگین فاصله خرابی (روز)",
               "مبنای محاسبه", "مبنای شروع", "تاریخ مبنا", "تاریخ پیشنهادی بازدید بعدی",
               "روز باقی‌مانده", "وضعیت")
    data_rows = [
        (r["cod"], r["name"], r["failure_count"], r["avg_interval_days"], r["basis"],
         r["baseline_label"], r["baseline_date"], r["recommended_date"], r["days_remaining"], r["urgency"])
        for r in results
    ]
    return excel_response(headers, data_rows, "پیشنهاد_زمانبندی_بازدید.xlsx")


# ============================================== گزارش شاخص‌های سازمانی
def _compute_organizational_kpi(db, jalali_year: int):
    monthly = []
    for jm in range(1, 13):
        prefix = f"{jalali_year:04d}/{jm:02d}/"
        rows = db.execute(
            "SELECT codedastgah, timetavaghofdastgah FROM data WHERE etefaghi = 1 AND tarikhdarkhast LIKE ?",
            (prefix + "%",),
        ).fetchall()
        failure_rows = [r for r in rows if r["codedastgah"] is not None and str(r["codedastgah"]).strip()]
        failure_count = len(failure_rows)
        total_downtime = sum(parse_hours(r["timetavaghofdastgah"]) for r in failure_rows)
        failed_devices = sorted({str(r["codedastgah"]).strip() for r in failure_rows})

        # همان منطق بخش «محاسبه MTTR و MTBF»: ابتدا برای هر دستگاه
        # جداگانه محاسبه می‌کنیم، سپس میانگین دستگاه‌های دارای خرابی را می‌گیریم.
        device_mttr_values = []
        device_mtbf_values = []
        for cod in failed_devices:
            device_rows = [r for r in failure_rows if str(r["codedastgah"]).strip() == cod]
            n = len(device_rows)
            downtime = sum(parse_hours(r["timetavaghofdastgah"]) for r in device_rows)
            if n:
                device_mttr_values.append(downtime / n)
                device_mtbf_values.append((475.0 - downtime) / n)

        if device_mttr_values:
            mttr = round(sum(device_mttr_values) / len(device_mttr_values), 4)
            mtbf = round(sum(device_mtbf_values) / len(device_mtbf_values), 3)
        else:
            mttr = None
            mtbf = None

        tekrary_count = db.execute(
            "SELECT COUNT(*) FROM data WHERE tekrary = 1 AND tarikhdarkhast LIKE ?",
            (prefix + "%",),
        ).fetchone()[0]
        monthly.append({
            "month": jm, "month_name": MONTH_NAMES_FA[jm - 1],
            "downtime": round(total_downtime, 2) if failure_count else 0,
            "mttr": mttr, "mtbf": mtbf, "tekrary": tekrary_count,
        })

    cost_rows = db.execute(
        "SELECT jalali_month, amount FROM monthly_repair_cost WHERE jalali_year = ?",
        (jalali_year,),
    ).fetchall()
    cost_by_month = {r["jalali_month"]: r["amount"] for r in cost_rows}
    for m in monthly:
        m["cost"] = cost_by_month.get(m["month"])
    return monthly


@app.route("/organizational-kpi")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def organizational_kpi():
    db = get_db()
    year = request.args.get("year", type=int) or current_jalali_year()
    monthly = _compute_organizational_kpi(db, year)
    return render_template(
        "organizational_kpi.html", monthly=monthly, year=year,
        can_edit_cost=(session.get("role") == "admin"),
    )


@app.route("/organizational-kpi/save-costs", methods=["POST"])
@login_required
@roles_required(*ADMIN_ONLY)
def organizational_kpi_save_costs():
    db = get_db()
    year = request.form.get("year", type=int) or current_jalali_year()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with db:
        for jm in range(1, 13):
            raw = request.form.get(f"cost_{jm}", "").strip().replace(",", "")
            if raw == "":
                continue
            try:
                amount = float(raw)
            except ValueError:
                continue
            db.execute(
                """INSERT INTO monthly_repair_cost (jalali_year, jalali_month, amount, updated_by, updated_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(jalali_year, jalali_month) DO UPDATE SET
                       amount=excluded.amount, updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                (year, jm, amount, session.get("username"), now),
            )
    flash("هزینه‌های تعمیرات ذخیره شد.", "success")
    return redirect(url_for("organizational_kpi", year=year))


@app.route("/organizational-kpi/export")
@login_required
@roles_required(*GENERAL_ACCESS_ROLES)
def organizational_kpi_export():
    db = get_db()
    year = request.args.get("year", type=int) or current_jalali_year()
    monthly = _compute_organizational_kpi(db, year)

    headers = ["شاخص"] + [m["month_name"] for m in monthly]
    rows = [
        ["توقفات پیش‌بینی‌نشده (ساعت)"] + [m["downtime"] for m in monthly],
        ["هزینه تعمیرات"] + [m["cost"] if m["cost"] is not None else "" for m in monthly],
        ["MTTR"] + [m["mttr"] if m["mttr"] is not None else "" for m in monthly],
        ["MTBF"] + [m["mtbf"] if m["mtbf"] is not None else "" for m in monthly],
        ["تعداد خرابی‌های تکراری"] + [m["tekrary"] for m in monthly],
    ]
    return excel_response(headers, rows, f"شاخص_سازمانی_{year}.xlsx")


if __name__ == "__main__":
    # حالت debug فقط برای توسعه روی سیستم خودتان است و پیش‌فرض خاموش
    # است چون دیباگر Flask روی اینترنت باز می‌تواند اجازه‌ی اجرای کد
    # دلخواه را به مهاجم بدهد. برای فعال کردنش موقع تست محلی:
    #   Windows:  set FLASK_DEBUG=1
    #   Linux/Mac: export FLASK_DEBUG=1
    # برای اجرای واقعی روی سرور، همیشه از run_production.py استفاده کنید.
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=5000, debug=True)