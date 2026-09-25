# تطبیق ERD تولید با CMMS فعلی

تاریخ: 2026-09-25

## نتیجه
در CMMS فعلی، جدول `dastgahjadid` موجودیت اصلی دستگاه است و `cod` کلید اصلی آن است. در کد برنامه، `data.codedastgah`، `mojry.kod_dastgah` و `mvademasrafi.kod_dastgah` به همین کد دستگاه اشاره می‌کنند.

## تصمیم برای تولید
`production_machines.cmms_device_code` به صورت منطقی به `dastgahjadid.cod` متصل شود. در migration اول FK فیزیکی ایجاد نشود تا داده‌های واقعی ابتدا اعتبارسنجی شوند.

`production_machines` شامل شناسه داخلی، code، name، cmms_device_code، station_id و is_active خواهد بود.

## ایستگاه
«دستگاه» در CMMS با «ایستگاه تولید» یکی فرض نمی‌شود. `production_stations` موجودیت مستقل تولید است و `production_machines.station_id` ماشین را به ایستگاه متصل می‌کند.

## توقف CMMS
در CMMS، درخواست خرابی در `data` ثبت می‌شود و فیلدهای `codedastgah`، `tarikhdarkhast`، `tarikhstart`، `timestart`، `tarikhend`، `timeEnd` و `timetavaghofdastgah` برای ارتباط توقف مهم‌اند. در تولید، `production_stops.source_type=cmms` و `cmms_request_id` برای ارجاع به توقف تعمیراتی پیش‌بینی شده‌اند.

قاعده: توقف CMMS نباید دوباره به صورت توقف دستی تولید ثبت شود.

## محصول
محصول تولید فعلاً master مستقل `production_products` است و ارتباط مستقیم با `kalajadid` هنوز قطعی نشده است. مجاز بودن محصول در ایستگاه با `production_station_products` کنترل می‌شود.

## زنجیره پیشنهادی
CMMS `dastgahjadid.cod`
→ `production_machines.cmms_device_code`
→ `production_machines.station_id`
→ `production_stations`
→ `production_station_products`
→ `production_products`

برای توقف:
CMMS `data`
→ `production_stops`
→ گزارش تولید / OEE

## موارد نیازمند اعتبارسنجی
- آیا هر دستگاه CMMS دقیقاً یک ماشین تولید است.
- آیا یک ماشین می‌تواند در چند ایستگاه استفاده شود.
- کد واقعی ایستگاه در Excel.
- آیا هر تولید به ماشین نیاز دارد یا فقط ایستگاه.
- تعریف تاریخ کاری شیفت شب.
- تبدیل توقف CMMS به دقیقه تولید.
- امکان تطبیق محصول تولید با `kalajadid.cod`.

این مرحله فقط مستندسازی است و هیچ migration یا جدول تولیدی ایجاد نشده است.
