# -*- coding: utf-8 -*-
"""
ماژول احراز هویت و کنترل دسترسی بر اساس نقش (RBAC).

نقش‌ها:
    admin      - دسترسی کامل (مدیریت کاربران، ثبت دستگاه/مجری/کالا، همه‌چیز)
    viewer     - فقط مشاهده (جستجو، جزئیات، گزارش‌ها) — بدون امکان ثبت یا تغییر
    requester  - سرپرست‌ها: مشاهده + ثبت درخواست خرابی + ثبت بازدید روزانه
    reviewer   - تعمیرات: مشاهده + بررسی و تکمیل درخواست‌ها + بازدید پیشگیرانه/پیش‌بینانه
    worker     - کارگر: فقط و فقط ثبت بازدید روزانه؛ به هیچ بخش دیگری (جستجو،
                 گزارش، حتی صفحه‌ی اصلی با محتوای دیگر) دسترسی ندارد

رمزهای عبور هرگز به‌صورت متن ساده ذخیره نمی‌شوند؛ فقط هش آن‌ها
(werkzeug.security) در دیتابیس نگه داشته می‌شود.
"""

from functools import wraps

from flask import session, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash

ROLES = {
    "admin": "مدیر سیستم",
    "viewer": "فقط مشاهده",
    "requester": "سرپرست‌ها",
    "reviewer": "تعمیرات",
    "worker": "کارگر",
}

# نقش‌هایی که اجازه‌ی ثبت درخواست خرابی (مرحله ۱) را دارند
CAN_CREATE_REQUEST = {"admin", "requester"}
# نقش‌هایی که اجازه‌ی بررسی و تکمیل درخواست (مرحله ۲) را دارند
CAN_REVIEW_REQUEST = {"admin", "reviewer"}
# نقش‌هایی که اجازه‌ی مدیریت دستگاه/مجری/کالا و کاربران را دارند
ADMIN_ONLY = {"admin"}
# نقش‌هایی که اجازه‌ی ثبت بازدید روزانه را دارند (کارگر هم اینجا اضافه شده)
CAN_DAILY_INSPECTION = {"admin", "requester", "worker"}
# نقش‌هایی که اجازه‌ی ثبت بازدید پیشگیرانه/پیش‌بینانه را دارند
CAN_PREVENTIVE_INSPECTION = {"admin", "reviewer"}
# همه‌ی نقش‌ها به‌جز کارگر — کارگر فقط به ثبت بازدید روزانه دسترسی دارد
# و از جستجو، گزارش‌ها، جزئیات درخواست و غیره محروم است
GENERAL_ACCESS_ROLES = {"admin", "viewer", "requester", "reviewer"}


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def current_user():
    if "user_id" not in session:
        return None
    return {
        "id": session["user_id"],
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "role": session.get("role"),
        "role_label": ROLES.get(session.get("role"), session.get("role")),
    }


def login_user(user_row):
    session["user_id"] = user_row["id"]
    session["username"] = user_row["username"]
    session["full_name"] = user_row["full_name"]
    session["role"] = user_row["role"]


def logout_user():
    session.clear()


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


def roles_required(*allowed_roles):
    """
    دکوریتور محدودسازی دسترسی: فقط کاربرانی که نقششان در allowed_roles
    باشد اجازه‌ی دسترسی به route را دارند. حتماً باید بعد از
    login_required استفاده شود (یا با آن ترکیب شود).
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login", next=request.path))
            if session.get("role") not in allowed_roles:
                flash("شما اجازه‌ی دسترسی به این بخش را ندارید.", "error")
                return redirect(url_for("index"))
            return view_func(*args, **kwargs)
        return wrapped
    return decorator
