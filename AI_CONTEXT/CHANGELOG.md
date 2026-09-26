## [2026-09-26] — رفع علت رد شدن POST تقویم کاری
- بررسی لاگ Windows Server و کد CSRF نشان داد POST به /production/work-calendar با 302 به / برمی‌گشت چون فرم POST توکن CSRF نداشت و check_csrf() درخواست را با 400 رد می‌کرد.
- فرم templates/production_work_calendar.html به hidden CSRF token مجهز شد.
- commit نهایی: f3056b4650bff0866125889a393f848101678e6d
- تست عملی روی Windows Server پس از این اصلاح هنوز انجام نشده است.

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

## [2026-09-26] — همسان‌سازی Control و migration طبقه‌بندی توقف
- توقف‌های is_planned_stop=1 در گزارش Control از unavailability حذف شدند.
- helper مشترک _stop_counts_as_unavailability اضافه شد.
- migration ستون production_stop_types.is_planned_stop در get_connection() فعال شد.
- تست رگرسیون طبقه‌بندی توقف اضافه شد.
- commits: 6d512d9, 60e5b96, 1925ad6, 6589187
