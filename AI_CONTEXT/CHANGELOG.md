## [2026-09-26] — تست رگرسیون aggregation گزارش‌های تولید
- فایل `tests/test_production_report_aggregation.py` اضافه شد.
- aggregation مورد استفاده OEE از نظر approved-only، چند Plan Item، حذف event بدون `plan_item_id` و تفکیک محصول/ایستگاه تست شد.
- این تست‌ها از double-count ناشی از joinهای چندمرحله‌ای جلوگیری می‌کنند.
- تست‌ها با SQLite in-memory اجراشدنی طراحی شده‌اند، اما pytest در محیط واقعی Windows/SQL Server هنوز اجرا نشده است.
- commit: daab9f01c3796c4986abb80ed2d9d8863919c260

# Changelog

## [2026-09-25] — ثبت برنامه پیاده‌سازی مرحله‌ای ماژول تولید
- فایل AI_CONTEXT/PRODUCTION_IMPLEMENTATION_PLAN.md ایجاد شد.
- فازهای پیاده‌سازی از master/planning تا OEE مشخص شدند.
- اصل migration کوچک، قابل rollback و بدون تغییر داده CMMS ثبت شد.
- commit: 14c4eb2cc066fb6de068343e15a7739dcea0e0a5

## [2026-09-25] — طراحی ERD منطقی مرحله اول ماژول تولید
- فایل AI_CONTEXT/PRODUCTION_ERD.md ایجاد شد.
- موجودیت‌های پایه، برنامه، حضور، تولید، توقف، ضایعات، مواد و تشویقی تعریف شدند.
- رابطه ماشین تولید با کد دستگاه CMMS به صورت منطقی مشخص شد.
- migration اجرایی هنوز ساخته نشده است.

## [2026-09-25] — تحلیل مرحله اول Excel ماژول تولید
- فایل AI_CONTEXT/PRODUCTION_EXCEL_ANALYSIS.md ایجاد شد.
- ساختار و وابستگی 25 شیت Excel مستندسازی شد.
- منطق OEE و جریان مواد استخراج شد.
- موارد #REF! ثبت شدند.
