# برنامه پیاده‌سازی مرحله اول ماژول تولید

تاریخ: 2026-09-25

## هدف
شروع پیاده‌سازی ماژول تولید بدون دست‌زدن به داده‌های فعلی CMMS و بدون migration گسترده.

## اصل اجرایی
هر مرحله باید:
1. مستقل و کوچک باشد.
2. قابل rollback باشد.
3. روی SQL Server فعلی قابل اجرا باشد.
4. هیچ داده فعلی CMMS را حذف یا تغییر ندهد.
5. قبل از استفاده عملیاتی تست شود.

## فاز 1 — Master Data و برنامه تولید
جداول اولیه:
- production_products
- production_suppliers
- production_raw_materials
- production_stations
- production_machines
- production_station_products
- production_employees
- production_shifts
- production_plans
- production_plan_items

### اتصال CMMS
production_machines.cmms_device_code به صورت منطقی با dastgahjadid.cod تطبیق داده می‌شود و در migration اول FK فیزیکی به CMMS ساخته نمی‌شود.

### محدودیت مهم
تا زمانی که داده واقعی محصولات، ایستگاه‌ها، پرسنل و ماشین‌ها با Excel و CMMS تطبیق داده نشده‌اند، import خودکار یا تبدیل انبوه انجام نمی‌شود.

## فاز 2
پس از تست فاز 1:
- production_attendance
- production_breaks_or_leave
- production_entries
- production_stop_types
- production_stops

## فاز 3
- production_defect_types
- production_waste_entries
- production_rework_entries
- گزارش کنترل تولید/ضایعات

## فاز 4
- production_inventory_transactions
- گردش رسید، تحویل به خط، تولید و ارسال

## فاز 5
- incentive و گزارش‌های کارکرد

## فاز 6
- گزارش مدیریتی و OEE

## قواعدی که قبل از محاسبات باید تثبیت شوند
- معادل آحاد و time_weight
- تعریف زمان کارکرد و حضور مفید
- طبقه‌بندی توقف و اثر آن بر OEE
- حد مجاز ضایعات
- فرمول تشویقی
- تاریخ کاری شیفت شب
- رابطه محصول/ایستگاه/ماشین