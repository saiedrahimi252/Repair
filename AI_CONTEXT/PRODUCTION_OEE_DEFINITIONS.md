# تعریف شاخص‌های OEE تولید

تاریخ: 2026-09-26

این سند مرجع محاسبات OEE در ماژول تولید است. هدف آن تثبیت تعریف‌ها قبل از ساخت گزارش نهایی OEE است.

## 1. Availability

در سطح تاریخ + شیفت + ایستگاه:

- Planned Minutes = زمان برنامه‌ریزی‌شده برای روز کاری.
- Planned Stop Minutes = اتحاد بازه‌های توقف‌هایی که `is_planned_stop=1` هستند.
- Net Planned Minutes = `max(Planned Minutes - Planned Stop Minutes, 0)`.
- Unplanned Unavailability Minutes = اتحاد بازه‌های توقف‌هایی که `counts_as_unavailability=1` و `is_planned_stop=0` هستند.
- Available Minutes = `max(Net Planned Minutes - Unplanned Unavailability Minutes, 0)`.
- Availability % = `Available Minutes / Net Planned Minutes × 100`.

همه بازه‌ها قبل از محاسبه به پنجره برنامه‌ریزی همان شیفت بریده می‌شوند و overlap نباید دوباره‌شماری شود.

روز غیرکاری (`is_working=0`) زمان برنامه‌ریزی تولید ندارد.

## 2. Quality

برای یک بازه گزارش:

- Total Production = مجموع تولید ثبت‌شده.
- Waste = مجموع رویدادهای `record_type='waste'`.
- Rework = مجموع رویدادهای `record_type='rework'`.
- Good Quantity = `max(Total Production - Waste - Rework, 0)`.
- Quality % = `Good Quantity / Total Production × 100`.

اگر Total Production صفر باشد، Quality قابل محاسبه نیست و باید «—» نمایش داده شود، نه صفر مصنوعی.

نکته: تا وقتی معنای دقیق «ثبت تولید» و اینکه مقدار تولید شامل قطعات دوباره‌کاری‌شده چگونه ثبت می‌شود تأیید نشده، این فرمول به‌عنوان تعریف فعلی گزارش باقی می‌ماند و نباید باعث حذف/تغییر داده‌های ثبت‌شده شود.

## 3. Performance

Performance فقط زمانی قابل محاسبه است که برای محصول/ایستگاه یک Cycle Time استاندارد معتبر داشته باشیم.

فرمول پایه:

`Performance % = Total Production × Standard Cycle Time Seconds / (Available Minutes × 60) × 100`

برای جلوگیری از نتیجه غیرواقعی، مقدار گزارش‌شده حداکثر 100% خواهد بود.

اگر Available Minutes صفر باشد یا Cycle Time معتبر (بزرگ‌تر از صفر و finite) وجود نداشته باشد، Performance «—» است.

### انتخاب Cycle Time

ترتیب پیشنهادی برای پیدا کردن زمان استاندارد:

1. `production_station_products.cycle_time_seconds` برای ترکیب محصول + ایستگاه، اگر مقدار معتبر داشته باشد.
2. در غیر این صورت `production_stations.cycle_time_seconds` به‌عنوان مقدار پیش‌فرض ایستگاه.

اگر هیچ‌کدام معتبر نباشند، Performance و در نتیجه OEE نباید حدس زده شوند.

## 4. OEE

پس از محاسبه سه شاخص:

- OEE = Availability × Performance × Quality

در پیاده‌سازی درصدی:

`OEE % = Availability % × Performance % × Quality % / 10000`

OEE فقط وقتی قابل محاسبه است که هر سه مؤلفه قابل محاسبه باشند.

## 5. تجمیع چند ردیف

برای بازه چندروزه/چندشیفته:

- Availability از مجموع Available Minutes / مجموع Net Planned Minutes محاسبه می‌شود.
- Quality از مجموع Good Quantity / مجموع Total Production محاسبه می‌شود.
- Performance با یک Cycle Time واحد فقط زمانی قابل تجمیع است که تمام تولیدهای واردشده در مخرج، Cycle Time استاندارد یکسان داشته باشند.
- اگر محصولات یا ایستگاه‌های مختلف Cycle Time متفاوت داشته باشند، Performance باید در سطح محصول + ایستگاه محاسبه و سپس با تعریف تجمیع صریح گزارش شود؛ نباید یک Cycle Time دلخواه برای کل مجموعه انتخاب شود.

## 6. محدودیت‌های فعلی

- OEE هنوز در UI فعال نشده است.
- توقف‌های CMMS هنوز به‌صورت کامل وارد محاسبه OEE نشده‌اند.
- Employee Break ها عمداً در Availability ماشین/ایستگاه وارد نمی‌شوند.
- معادل آحاد و time_weight هنوز برای Performance جایگزین Cycle Time نشده‌اند.
- رفتار دقیق Rework در تعریف Good Quantity باید با فرآیند واقعی ثبت تولید کنترل شود.

## 7. اصل مهم

هیچ مقدار OEE/Performance با حدس یا fallback مبهم تولید نشود. نبود داده استاندارد باید با «قابل محاسبه نیست» مشخص شود.


## 2026-09-26 — Mixed products in one station/shift
When more than one product is present for the same work date + shift + station, the station's Available Minutes are shared time and cannot safely be assigned in full to every product row. Until an explicit time-allocation rule is approved, Availability may be shown at the shared station level, but Performance and OEE for those product rows are intentionally not calculated. This prevents double allocation of the same available minutes and avoids understated Performance caused by reusing the full station time for each product.
