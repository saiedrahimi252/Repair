# Current Task

## هدف اصلی فعلی
پیاده‌سازی مرحله‌ای ماژول «تولید» در نرم‌افزار Repair بر اساس Excel تولیدی بررسی‌شده در 2026-09-25.

## مرحله فعلی
تثبیت طراحی و آماده‌سازی فاز 1. migration اجرایی هنوز اجرا نشده است.

## کارهای انجام‌شده
- ساختار 25 شیت Excel شناسایی شد.
- وابستگی‌های اصلی و جریان مواد استخراج شد.
- منطق اولیه OEE استخراج شد.
- خطاهای #REF! ثبت شدند.
- ERD منطقی مرحله اول ساخته شد.
- تطبیق اولیه ERD با database.py و CMMS انجام شد.
- برنامه پیاده‌سازی مرحله‌ای در AI_CONTEXT/PRODUCTION_IMPLEMENTATION_PLAN.md ثبت شد.

## کارهای باقی‌مانده فاز فعلی
- اعتبارسنجی معادل آحاد و time_weight.
- اعتبارسنجی زمان حضور مفید/کارکرد برنامه‌ای/کارکرد ساعت‌زن.
- تعریف رسمی انواع توقف و اثر آنها بر OEE.
- تعریف حد مجاز ضایعات.
- استخراج فرمول کامل تشویقی.
- تثبیت تاریخ کاری شیفت شب.
- نهایی‌کردن رابطه محصول، ایستگاه و ماشین.
- مشخص‌کردن نقش‌های واقعی تولید.

## فاز 1 بعد از تثبیت
Master Data و برنامه تولید:
production_products, production_suppliers, production_raw_materials, production_stations, production_machines, production_station_products, production_employees, production_shifts, production_plans, production_plan_items.

## محدودیت
تا قبل از تثبیت منطق و کلیدها، migration گسترده یا import انبوه انجام نشود. اتصال production_machines به dastgahjadid.cod در ابتدا منطقی/کنترلی باشد و FK فیزیکی ایجاد نشود.
