# -*- coding: utf-8 -*-
"""مدیریت چندشرکتی سیستم تعمیرات و پلن‌های دسترسی."""

import datetime
import re
import pyodbc

from database import Connection, _build_connection_string, get_connection
from auth import hash_password

PLANS = {
    "free": {"name": "رایگان", "max_users": 20, "max_devices": 50},
    "pro": {"name": "حرفه‌ای", "max_users": 100, "max_devices": 250},
    "enterprise": {"name": "سازمانی", "max_users": None, "max_devices": None},
}


def _safe_db_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip())
    value = value.strip("_") or "company"
    return value[:80]


def master_connection():
    raw = pyodbc.connect(_build_connection_string("master"), autocommit=False)
    return Connection(raw)


def ensure_master_database():
    """دیتابیس مدیریتی را می‌سازد و شرکت فعلی را به‌عنوان شرکت اول ثبت می‌کند."""
    root = master_connection()
    try:
        exists = root.execute(
            "SELECT 1 FROM sys.databases WHERE name = ?", ("repair_master",)
        ).fetchone()
        if not exists:
            # SQL Server اجازه CREATE DATABASE را داخل تراکنش نمی‌دهد.
            # این اتصال عمداً با autocommit=True باز می‌شود.
            raw_root = pyodbc.connect(_build_connection_string("master"), autocommit=True)
            try:
                raw_root.execute("CREATE DATABASE [repair_master]")
            finally:
                raw_root.close()
    finally:
        root.close()

    db = master_connection_to("repair_master")
    try:
        db.execute("""
            IF OBJECT_ID('dbo.companies','U') IS NULL
            BEGIN
                CREATE TABLE companies (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    name NVARCHAR(255) NOT NULL UNIQUE,
                    db_name NVARCHAR(128) NOT NULL UNIQUE,
                    plan_code NVARCHAR(30) NOT NULL DEFAULT 'free',
                    is_active INT NOT NULL DEFAULT 1,
                    starts_at NVARCHAR(40),
                    expires_at NVARCHAR(40),
                    created_at NVARCHAR(40) NOT NULL,
                    notes NVARCHAR(MAX)
                )
            END
        """)
        db.execute("""
            IF OBJECT_ID('dbo.master_users','U') IS NULL
            BEGIN
                CREATE TABLE master_users (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    username NVARCHAR(255) NOT NULL UNIQUE,
                    password_hash NVARCHAR(MAX) NOT NULL,
                    full_name NVARCHAR(MAX),
                    is_active INT NOT NULL DEFAULT 1,
                    created_at NVARCHAR(40) NOT NULL
                )
            END
        """)
        db.commit()

        count = db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if count == 0:
            db.execute(
                """INSERT INTO companies
                   (name, db_name, plan_code, is_active, starts_at, created_at, notes)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    "شرکت قطعه سازان ايتوک", "repair", "enterprise", 1,
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    "شرکت اول؛ دیتابیس repair فعلی حفظ شده است.",
                ),
            )
            db.commit()
    finally:
        db.close()


def master_connection_to(database_name):
    raw = pyodbc.connect(_build_connection_string(database_name), autocommit=False)
    return Connection(raw)


def master_users_exist():
    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        return db.execute("SELECT COUNT(*) FROM master_users").fetchone()[0] > 0
    finally:
        db.close()


def create_master_user(username, password, full_name):
    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        db.execute(
            "INSERT INTO master_users (username,password_hash,full_name,created_at) VALUES (?,?,?,?)",
            (username, hash_password(password), full_name, datetime.datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
    finally:
        db.close()


def verify_master_user(username, password):
    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        row = db.execute("SELECT * FROM master_users WHERE username = ?", (username,)).fetchone()
        if not row or not row["is_active"]:
            return None
        from auth import verify_password
        if not verify_password(password, row["password_hash"]):
            return None
        return row
    finally:
        db.close()


def list_companies():
    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        rows = db.execute("SELECT * FROM companies ORDER BY id").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            plan = PLANS.get(item["plan_code"], PLANS["free"])
            company_db = get_connection(item["db_name"])
            try:
                item["user_count"] = company_db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                item["device_count"] = company_db.execute("SELECT COUNT(*) FROM dastgahjadid").fetchone()[0]
            finally:
                company_db.close()
            item["plan_name"] = plan["name"]
            item["max_users"] = plan["max_users"]
            item["max_devices"] = plan["max_devices"]
            result.append(item)
        return result
    finally:
        db.close()


def get_company(company_id):
    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        return db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    finally:
        db.close()


def create_company(name, admin_username, admin_password, admin_full_name, plan_code):
    if plan_code not in PLANS:
        raise ValueError("پلن نامعتبر است.")
    name = (name or "").strip()
    admin_username = (admin_username or "").strip()
    admin_full_name = (admin_full_name or "").strip()
    if not name or not admin_username or len(admin_password or "") < 8:
        raise ValueError("نام شرکت، نام کاربری مدیر و رمز حداقل ۸ کاراکتری الزامی است.")

    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        if db.execute("SELECT 1 FROM companies WHERE name = ?", (name,)).fetchone():
            raise ValueError("این نام شرکت قبلاً ثبت شده است.")
        if db.execute("SELECT 1 FROM companies WHERE db_name = ?", (_safe_db_name("repair_" + name),)).fetchone():
            raise ValueError("نام دیتابیس شرکت تکراری است.")

        base = _safe_db_name("repair_" + name)
        candidate = base
        n = 2
        while db.execute("SELECT 1 FROM companies WHERE db_name = ?", (candidate,)).fetchone():
            candidate = f"{base[:70]}_{n}"
            n += 1

        # CREATE DATABASE باید خارج از تراکنش اجرا شود.
        raw_root = pyodbc.connect(_build_connection_string("master"), autocommit=True)
        try:
            raw_root.execute(f"CREATE DATABASE [{candidate.replace(']', ']]')}]")
        finally:
            raw_root.close()

        company_db = get_connection(candidate)
        try:
            if company_db.execute("SELECT 1 FROM users WHERE username = ?", (admin_username,)).fetchone():
                raise ValueError("نام کاربری مدیر در این شرکت تکراری است.")
            company_db.execute(
                "INSERT INTO users (username,password_hash,full_name,role,created_at) VALUES (?,?,?,?,?)",
                (admin_username, hash_password(admin_password), admin_full_name, "admin",
                 datetime.datetime.now().isoformat(timespec="seconds")),
            )
            company_db.commit()
        finally:
            company_db.close()

        now = datetime.datetime.now().isoformat(timespec="seconds")
        db.execute(
            """INSERT INTO companies
               (name,db_name,plan_code,is_active,starts_at,created_at)
               VALUES (?,?,?,?,?,?)""",
            (name, candidate, plan_code, 1, now, now),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_company(company_id, plan_code=None, is_active=None, expires_at=None):
    if plan_code is not None and plan_code not in PLANS:
        raise ValueError("پلن نامعتبر است.")
    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise ValueError("شرکت پیدا نشد.")
        new_plan = plan_code if plan_code is not None else row["plan_code"]
        new_active = int(is_active) if is_active is not None else row["is_active"]
        new_expiry = expires_at if expires_at is not None else row["expires_at"]
        db.execute(
            "UPDATE companies SET plan_code=?, is_active=?, expires_at=? WHERE id=?",
            (new_plan, new_active, new_expiry, company_id),
        )
        db.commit()
    finally:
        db.close()


def company_limit(company_id, kind):
    row = get_company(company_id)
    if not row:
        return None, 0, None
    plan = PLANS.get(row["plan_code"], PLANS["free"])
    db = get_connection(row["db_name"])
    try:
        table = "users" if kind == "users" else "dastgahjadid"
        count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        db.close()
    maximum = plan["max_users"] if kind == "users" else plan["max_devices"]
    return row, count, maximum


def record_master_access(master_user_id, company_id, company_name, ip_address):
    """ثبت ورود مدیر اصلی به پنل یک شرکت برای ممیزی."""
    ensure_master_database()
    db = master_connection_to("repair_master")
    try:
        db.execute("""
            IF OBJECT_ID('dbo.master_access_log','U') IS NULL
            BEGIN
                CREATE TABLE master_access_log (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    master_user_id INT,
                    company_id INT,
                    company_name NVARCHAR(255),
                    access_time NVARCHAR(40) NOT NULL,
                    ip_address NVARCHAR(100)
                )
            END
        """)
        db.execute(
            """INSERT INTO master_access_log
               (master_user_id, company_id, company_name, access_time, ip_address)
               VALUES (?,?,?,?,?)""",
            (master_user_id, company_id, company_name,
             datetime.datetime.now().isoformat(timespec="seconds"), ip_address),
        )
        db.commit()
    finally:
        db.close()


def company_allowed(company_id):
    row = get_company(company_id)
    if not row or not row["is_active"]:
        return False
    expires = row["expires_at"]
    if expires:
        try:
            return datetime.datetime.fromisoformat(expires) >= datetime.datetime.now()
        except ValueError:
            pass
    return True
