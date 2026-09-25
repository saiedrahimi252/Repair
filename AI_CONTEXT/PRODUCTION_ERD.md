# ERD منطقی مرحله اول ماژول تولید

تاریخ: 2026-09-25

این سند طراحی منطقی مرحله اول دیتابیس تولید است. هنوز migration اجرایی نیست و نباید مستقیماً روی سرور اجرا شود.

## 1. موجودیت‌های پایه

### production_products
- id PK
- code UNIQUE
- name
- unit
- is_active
- created_at

### production_customers
- id PK
- code UNIQUE
- name
- is_active

### production_suppliers
- id PK
- code UNIQUE
- name
- is_active

### production_raw_materials
- id PK
- code UNIQUE
- name
- unit
- supplier_id FK -> production_suppliers.id
- is_active

### production_stations
- id PK
- code UNIQUE
- name
- stage_name
- standard_qty_8h
- standard_qty_1h
- cycle_time_seconds
- time_weight
- previous_station_id NULL FK -> production_stations.id
- is_active

### production_machines
پل بین تولید و CMMS:
- id PK
- code UNIQUE
- name
- cmms_device_code NULL
- station_id FK -> production_stations.id
- is_active

در مرحله اول cmms_device_code باید به کد دستگاه فعلی CMMS یعنی dastgahjadid.cod متصل شود. فعلاً بهتر است این اتصال منطقی/کنترلی باشد و FK فیزیکی بعد از تثبیت ساختار بررسی شود.

### production_station_products
- id PK
- station_id FK
- product_id FK
- standard_cycle_time_seconds NULL
- standard_qty_1h NULL
- allowed_waste_percent NULL
- is_active
- UNIQUE(station_id, product_id)

### production_employees
- id PK
- personnel_code UNIQUE
- full_name
- is_active
- user_id NULL

user_id فقط در صورت نیاز به اتصال اپراتور به حساب ورود وب استفاده شود.

### production_shifts
- id PK
- code UNIQUE
- name
- start_time
- end_time
- crosses_midnight
- is_active

## 2. برنامه تولید

### production_plans
- id PK
- plan_date
- status (draft/approved/closed)
- created_by
- approved_by NULL
- created_at
- approved_at NULL
- notes

### production_plan_items
- id PK
- plan_id FK
- product_id FK
- station_id NULL FK
- target_qty
- management_target_qty NULL
- work_day
- notes

## 3. حضور

### production_attendance
- id PK
- work_date
- employee_id FK
- shift_id FK
- check_in_datetime
- check_out_datetime NULL
- attendance_minutes
- status
- notes

برای شیفت شب، تاریخ کاری و timestamp واقعی ورود/خروج جدا حفظ شوند.

### production_breaks_or_leave
- id PK
- attendance_id NULL FK
- employee_id FK
- work_date
- start_datetime
- end_datetime
- minutes
- leave_type
- approved_by NULL
- notes

## 4. تولید و توقف

### production_entries
مهم‌ترین جدول عملیاتی:
- id PK
- production_datetime
- work_date
- shift_id FK
- employee_id FK
- product_id FK
- station_id FK
- machine_id NULL FK
- quantity
- good_quantity NULL
- status (draft/confirmed/cancelled)
- entered_by
- confirmed_by NULL
- confirmed_at NULL
- notes
- created_at

### production_stop_types
- id PK
- code UNIQUE
- name
- category
- affects_availability
- affects_performance
- planned
- is_active

### production_stops
- id PK
- work_date
- shift_id FK
- station_id FK
- machine_id NULL FK
- start_datetime
- end_datetime NULL
- duration_minutes
- stop_type_id FK
- source_type (manual/cmms)
- cmms_request_id NULL
- description
- created_by
- created_at

توقف CMMS نباید دوباره به صورت توقف دستی ثبت شود.

## 5. ضایعات و دوباره‌کاری

### production_defect_types
- id PK
- code UNIQUE
- name
- is_active

### production_waste_entries
- id PK
- production_entry_id NULL FK
- work_date
- shift_id FK
- employee_id FK
- product_id FK
- station_id FK
- defect_type_id FK
- quantity
- waste_form
- status
- created_by
- created_at
- notes

### production_rework_entries
- id PK
- production_entry_id NULL FK
- work_date
- employee_id FK
- product_id FK
- station_id FK
- defect_type_id NULL FK
- quantity
- status
- created_by
- created_at

## 6. گردش مواد و محصول

پیشنهاد مرحله اول: یک ledger تراکنشی به جای چند جدول موجودی مستقل.

### production_inventory_transactions
- id PK
- transaction_datetime
- transaction_type (receipt/line_issue/consumption/production/dispatch/adjustment)
- raw_material_id NULL FK
- product_id NULL FK
- quantity
- unit
- reference_type
- reference_id
- from_location NULL
- to_location NULL
- created_by
- created_at
- notes

نگاشت Excel:
- رسید -> receipt
- تحویل به خط -> line_issue
- تولید -> production
- ارسال -> dispatch
- اصلاح موجودی -> adjustment

## 7. تشویقی

### production_incentive_runs
- id PK
- period_year
- period_month
- incentive_type
- status
- created_by
- approved_by NULL
- created_at
- approved_at NULL

### production_incentive_items
- id PK
- run_id FK
- employee_id FK
- planned_minutes
- useful_minutes
- worked_minutes
- incentive_amount NULL
- deduction_amount NULL
- calculation_note
- status

فرمول تشویقی هنوز نیازمند اعتبارسنجی است.

## 8. گزارش‌ها

فعلاً برای کارکرد روزانه، گزارش کارکرد، تولید ایستگاه، کنترل، گزارش مدیریتی و OEE جدول snapshot جدا نسازیم. این‌ها باید از Query/View یا سرویس Python محاسبه شوند.

## 9. روابط اصلی

products -> station_products -> stations -> machines
employees -> attendance -> breaks
employees -> production_entries -> products/stations/machines
production_entries -> waste_entries / rework_entries
plans -> plan_items -> products/stations
production_stops -> station/machine
production_stops -> CMMS request/reference
inventory_transactions -> raw_materials/products
incentive_runs -> incentive_items -> employees

## 10. قواعد یکپارچگی

1. تولید بدون محصول، ایستگاه و اپراتور معتبر ثبت نشود.
2. محصول فقط در ایستگاه مجاز همان محصول ثبت شود، مگر override مجاز.
3. مقدار تولید و ضایعات منفی نباشد.
4. پایان توقف قبل از شروع آن نباشد.
5. توقف CMMS دوباره به صورت دستی ثبت نشود.
6. رکورد تأییدشده تولید مستقیم و بدون تاریخچه قابل ویرایش نباشد.
7. حذف تراکنش‌های عملیاتی ترجیحاً cancel/soft-delete باشد.
8. موجودی از ledger محاسبه شود.
9. ضایعات مجاز از تنظیمات محصول/ایستگاه بیاید.
10. OEE فقط از رکوردهای تأییدشده و بازه مشخص محاسبه شود.

## 11. موارد نیازمند تأیید قبل از migration

- کلید واقعی اتصال ماشین تولید به dastgahjadid.cod
- آیا هر تولید حتماً machine نیاز دارد یا فقط station
- تعریف work_date برای شیفت شب
- فرمول معادل آحاد
- فرمول تشویقی
- فهرست و اثر انواع توقف
- حد مجاز ضایعات برای هر محصول/ایستگاه
- ساختار رسمی انبار و محل‌ها
- ثبت و تأیید تولید توسط چه نقش‌هایی

## نتیجه

این ERD عمداً کوچک و قابل توسعه است. هدف، ساخت پایه‌ای برای برنامه، حضور، تولید، توقف، ضایعات، مواد و گزارش‌هاست؛ نه تبدیل مستقیم فرمول‌های Excel به ستون‌های SQL.
