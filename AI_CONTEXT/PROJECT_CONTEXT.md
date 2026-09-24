# Project Context — Repair

## شناسنامه
- Repository: `saiedrahimi252/Repair`
- Branch اصلی فعلی: `main`
- نوع پروژه: Python Web Application
- دیتابیس: Microsoft SQL Server
- دسترسی دیتابیس از Python: `pyodbc`
- فایل اجرای production: `run_production.py`

## ساختار مهم
فایل‌های اصلی فعلی Repository شامل:
- `app.py` — منطق اصلی برنامه و routeهای وب
- `auth.py` — احراز هویت
- `database.py` — لایه اتصال/سازگارسازی SQL Server
- `import_legacy_data.py` — وارد کردن داده‌های قدیمی
- `jalali.py` — توابع مرتبط با تاریخ جلالی
- `text_utils.py` — توابع کمکی متن
- `run_production.py` — اجرای production
- `repair_sqlserver.sql` — ساختار/داده SQL Server
- `requirements.txt` — وابستگی‌های Python
- `templates/` — قالب‌های HTML
- `.env.example` — نمونه تنظیمات اتصال

## معماری دیتابیس
`database.py` با `pyodbc` به SQL Server وصل می‌شود و بخشی از SQL به سبک SQLite موجود در برنامه را به T-SQL تبدیل می‌کند.

تنظیمات مهم محیطی:
- `MSSQL_SERVER`
- `MSSQL_DATABASE`
- `MSSQL_UID`
- `MSSQL_PWD`
- `MSSQL_DRIVER`
- `MSSQL_TRUSTED_CONNECTION`
- `MSSQL_ENCRYPT`
- `MSSQL_TRUST_SERVER_CERTIFICATE`

مقدار پیش‌فرض در کد برای Driver، `ODBC Driver 18 for SQL Server` است.

## نکته مهم
README فعلی می‌گوید برنامه از SQL Server استفاده می‌کند و اگر دیتابیس از صفر ساخته شود، برنامه می‌تواند جدول‌های لازم را در اولین اجرا ایجاد کند. همچنین `repair_sqlserver.sql` برای آماده‌سازی دیتابیس وجود دارد.

## وضعیت فعلی
این فایل یک مرجع پایه است. وضعیت واقعی کار باید همیشه در `HANDOFF.md` ثبت شود.
