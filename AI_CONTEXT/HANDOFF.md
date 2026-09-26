# Handoff — وضعیت تحویل کار بین AIها

## تاریخ آخرین به‌روزرسانی
2026-09-26

## وضعیت فعلی
- مشکل ثبت تقویم کاری تولید روی Windows Server بررسی شد.
- GET مسیر /production/work-calendar با 200 انجام می‌شود، اما POST با 302 به / برمی‌گردد.
- بررسی app.py نشان داد check_csrf() همه POSTها را بررسی می‌کند و نبودن token باعث 400 و سپس redirect به / می‌شود.
- بررسی templates/production_work_calendar.html نشان داد فرم POST تقویم کاری فاقد hidden CSRF token بوده است.
- فرم با hidden field مربوط به csrf_token اصلاح شد.
- commit نهایی: f3056b4650bff0866125889a393f848101678e6d
- تست عملی جدید روی Windows Server هنوز انجام نشده است.

## قدم بعدی
1. deploy/restart نسخه f3056b4650bff0866125889a393f848101678e6d.
2. ورود مجدد به /production/work-calendar و ثبت همان داده قبلی.
3. اگر هنوز خطا وجود داشت، لاگ POST و پیام flash دقیق بررسی شود.
4. سپس تست عملی سایر فرم‌های تولید از نظر CSRF و SQL Server ادامه یابد.
