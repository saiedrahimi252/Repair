# -*- coding: utf-8 -*-
"""
تبدیل تاریخ میلادی به شمسی، بدون نیاز به کتابخانه‌ی خارجی (jdatetime در
دسترس نبود). الگوریتم استاندارد تبدیل میلادی به جلالی/شمسی.

داده‌های قدیمی این پروژه همگی به فرمت شمسی «۱۴۰۴/۰۶/۰۳» ذخیره شده‌اند؛
این ماژول باعث می‌شود مقادیر پیش‌فرض تاریخ در فرم‌ها (مثل «امروز») هم
با همان فرمت شمسی نمایش داده شوند، نه میلادی.
"""

import datetime


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1

    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1
    g_day_no += gd2

    j_day_no = g_day_no - 79

    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    for i in range(11):
        if j_day_no < j_days_in_month[i]:
            jm = i + 1
            jd = j_day_no + 1
            break
        j_day_no -= j_days_in_month[i]
    else:
        jm = 12
        jd = j_day_no + 1

    return jy, jm, jd


def today_jalali_str() -> str:
    """تاریخ امروز به فرمت شمسی «۱۴۰۴/۰۶/۰۳»."""
    now = datetime.date.today()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def now_time_str() -> str:
    """ساعت فعلی «HH:MM» (ساعت مستقل از تقویم است، نیازی به تبدیل ندارد)."""
    return datetime.datetime.now().strftime("%H:%M")


def jalali_to_gregorian(jy: int, jm: int, jd: int):
    """معکوس gregorian_to_jalali — برای محاسبه‌ی فاصله‌ی روز بین دو تاریخ شمسی لازم است."""
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    jy2 = jy - 979
    jm2 = jm - 1
    jd2 = jd - 1

    j_day_no = 365 * jy2 + (jy2 // 33) * 8 + ((jy2 % 33) + 3) // 4
    for i in range(jm2):
        j_day_no += j_days_in_month[i]
    j_day_no += jd2

    g_day_no = j_day_no + 79

    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097

    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False

    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461

    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365

    gm = 0
    days = g_days_in_month[:]
    if (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0:
        days[1] = 29
    for i in range(12):
        if g_day_no < days[i]:
            gm = i + 1
            gd = g_day_no + 1
            break
        g_day_no -= days[i]
    else:
        gm = 12
        gd = g_day_no + 1

    return gy, gm, gd


def parse_jalali_date(date_str):
    """
    «۱۴۰۴/۰۶/۰۳» را به datetime.date (میلادی، برای محاسبات ریاضی روی
    تاریخ) تبدیل می‌کند. برای رشته‌های نامعتبر یا خالی، None برمی‌گرداند.
    """
    if not date_str:
        return None
    parts = str(date_str).strip().split("/")
    if len(parts) != 3:
        return None
    try:
        jy, jm, jd = int(parts[0]), int(parts[1]), int(parts[2])
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        return datetime.date(gy, gm, gd)
    except (ValueError, TypeError):
        return None


def add_days_to_jalali_str(date_str: str, days: int) -> str:
    """یک تاریخ شمسی را می‌گیرد، تعداد روز مشخصی به آن اضافه می‌کند و تاریخ شمسی جدید را برمی‌گرداند."""
    base = parse_jalali_date(date_str)
    if base is None:
        return ""
    new_date = base + datetime.timedelta(days=days)
    jy, jm, jd = gregorian_to_jalali(new_date.year, new_date.month, new_date.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def jalali_days_in_month(jy: int, jm: int) -> int:
    """تعداد روزهای یک ماه شمسی خاص را برمی‌گرداند (با تبدیل به میلادی، نیازی به فرمول جداگانه‌ی کبیسه ندارد)."""
    if jm == 12:
        next_y, next_m = jy + 1, 1
    else:
        next_y, next_m = jy, jm + 1
    g1 = jalali_to_gregorian(jy, jm, 1)
    g2 = jalali_to_gregorian(next_y, next_m, 1)
    d1 = datetime.date(*g1)
    d2 = datetime.date(*g2)
    return (d2 - d1).days


def current_jalali_year() -> int:
    jy, _, _ = gregorian_to_jalali(*datetime.date.today().timetuple()[:3])
    return jy


MONTH_NAMES_FA = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
