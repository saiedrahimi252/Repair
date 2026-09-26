# Handoff — وضعیت تحویل کار بین AIها

## تاریخ آخرین به‌روزرسانی
2026-09-26

## وضعیت فعلی
- ممیزی فنی گزارش‌های OEE و Performance/Quality ادامه یافته است.
- منطق OEE برای approved planها و aggregation بر اساس `plan_item_id` بررسی و تست رگرسیون آن اضافه شد.
- رویدادهای بدون `plan_item_id` در aggregation محصول/ایستگاه عمداً کنار گذاشته می‌شوند.
- safeguard چندمحصولی حفظ شده است: در یک ایستگاه/شیفت با چند محصول، Quality/Availability قابل گزارش‌اند ولی Performance/OEE به‌دلیل نبود روش تخصیص زمان مشترک محاسبه نمی‌شوند.
- محدودیت چندماشینه همچنان مستند است و ظرفیت موازی مدل نشده است.
- migration اجرایی و اجرای واقعی روی Windows Server هنوز انجام نشده است.

## آخرین تغییر این مرحله
Commit:
- `daab9f01c3796c4986abb80ed2d9d8863919c260` — افزودن تست‌های رگرسیون aggregation گزارش تولید

فایل:
- `tests/test_production_report_aggregation.py`

پوشش تست:
1. plan غیر approved وارد مجموع نمی‌شود.
2. چند Plan Item برای یک محصول بدون double-count جمع می‌شوند.
3. event بدون `plan_item_id` وارد aggregation محصول/ایستگاه نمی‌شود.
4. محصول/ایستگاه دیگر در مجموع مخلوط نمی‌شود.

این تست‌ها با SQLite in-memory، شکل SQL aggregation فعلی OEE را بررسی می‌کنند؛ این جایگزین اجرای pytest در محیط واقعی SQL Server/Windows نیست.

## تست
- تست‌های جدید در repository اضافه شده‌اند.
- pytest واقعی روی Windows Server هنوز اجرا نشده است.
- اجرای واقعی برنامه و migration نیز هنوز انجام نشده است.

## مشکلات/کارهای باز
- اعتبارسنجی business ruleهای Excel: واحدها، time_weight، زمان کارکرد، انواع توقف، حد ضایعات، تشویقی، تاریخ کاری شیفت شب و نقش‌های تولید.
- بازبینی نهایی queryهای Performance/Quality، به‌خصوص جلوگیری از دوباره‌شماری و همسانی کامل با OEE.
- بررسی دوباره‌کاری/ضایعات و سایر event aggregationها.
- طراحی migration کوچک و قابل rollback پس از تثبیت قواعد.
- تست روی DB آزمایشی و سپس Windows Server.

## قدم بعدی دقیق
1. اجرای بازبینی SQLهای Performance/Quality و Control در برابر قواعد OEE.
2. اضافه‌کردن تست رگرسیون برای waste/rework aggregation و approved-only behavior در صورت وجود gap.
3. سپس اجرای pytest در محیط واقعی کاربر و ثبت نتیجه بدون ادعای موفقیت تا زمان اجرای واقعی.
4. بعد از تثبیت تست‌ها، سراغ migration آزمایشی برویم؛ نه قبل از آن.
