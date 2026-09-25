# -*- coding: utf-8 -*-
"""
لایه دیتابیس نسخه‌ی تحت وب — نسخه‌ی SQL Server.

این فایل جایگزین نسخه‌ی قبلی (SQLite) شده است. تمام بقیه‌ی برنامه
(app.py، import_legacy_data.py و ...) دقیقاً مثل قبل با شیء برگشتی
``get_connection()`` کار می‌کنند: ``db.execute(sql, params)``,
``db.commit()``, ``db.rollback()``, ``db.close()``, ``with db: ...``
و ردیف‌ها هم مثل قبل هم با ایندکس عددی (``row[0]``) و هم با نام
ستون (``row["col"]``) قابل خواندن‌اند — یعنی هیچ تغییری در app.py
لازم نبوده و نیست.

پشت‌صحنه این فایل با pyodbc به SQL Server وصل می‌شود و به‌صورت
خودکار دستورهای مخصوص SQLite که در بقیه‌ی کد وجود دارند (مثل
``INSERT OR IGNORE``، ``ON CONFLICT ... DO UPDATE``، ``PRAGMA``,
``LIMIT``, ``GLOB`` و ...) را به معادل T-SQL ترجمه می‌کند.

تنظیمات اتصال از متغیرهای محیطی خوانده می‌شوند (به .env.example
نگاه کنید):

    MSSQL_SERVER        آدرس سرور، مثل localhost یا myserver.database.windows.net
    MSSQL_DATABASE       نام دیتابیس
    MSSQL_UID             نام کاربری (اگر از Windows/Trusted Auth استفاده
                           نمی‌کنید)
    MSSQL_PWD             رمز عبور
    MSSQL_DRIVER          نام درایور ODBC نصب‌شده روی سرور
                           (پیش‌فرض: "ODBC Driver 18 for SQL Server")
    MSSQL_TRUSTED_CONNECTION   اگر "1" باشد از Windows Authentication
                                 استفاده می‌شود (بدون UID/PWD)
    MSSQL_ENCRYPT          پیش‌فرض "yes" (لازم برای درایور 18)
    MSSQL_TRUST_SERVER_CERTIFICATE   پیش‌فرض "yes" برای سرورهای داخلی
                                        بدون گواهی معتبر عمومی
"""

import os
import re
from collections.abc import Mapping

import pyodbc

try:  # بارگذاری اختیاری فایل .env در توسعه‌ی محلی
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass


# ============================================================== connection

def _build_connection_string(database_override: str = None) -> str:
    requested_driver = os.environ.get("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server").strip()
    installed_drivers = pyodbc.drivers()

    # اگر .env یا تنظیمات قدیمی به درایوری اشاره کند که روی این ویندوز
    # نصب نیست، به‌صورت خودکار از یکی از درایورهای موجود استفاده کن.
    driver = requested_driver
    if driver not in installed_drivers:
        preferred = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ]
        driver = next((name for name in preferred if name in installed_drivers), "")
    if not driver:
        raise RuntimeError(
            "هیچ ODBC Driver سازگار با SQL Server پیدا نشد. "
            f"درایورهای نصب‌شده: {installed_drivers}"
        )

    server = os.environ.get("MSSQL_SERVER", r"localhost\SQLEXPRESS")
    port = os.environ.get("MSSQL_PORT", "").strip()
    server_part = f"{server},{port}" if port else server
    database = database_override or os.environ.get("MSSQL_DATABASE", "repair")
    encrypt = os.environ.get("MSSQL_ENCRYPT", "yes")
    trust_cert = os.environ.get("MSSQL_TRUST_SERVER_CERTIFICATE", "yes")

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server_part}",
        f"DATABASE={database}",
        f"Encrypt={encrypt}",
        f"TrustServerCertificate={trust_cert}",
    ]

    trusted = os.environ.get("MSSQL_TRUSTED_CONNECTION", "1") == "1"
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        uid = os.environ.get("MSSQL_UID", "")
        pwd = os.environ.get("MSSQL_PWD", "")
        parts.append(f"UID={uid}")
        parts.append(f"PWD={pwd}")

    return ";".join(parts)


# ================================================================== Row

class Row(Mapping):
    """
    شبیه‌سازی sqlite3.Row: هم با نام ستون (row["x"]) و هم با ایندکس
    عددی (row[0]) قابل خواندن است. dict(row) و row.keys() هم کار
    می‌کنند (چون از Mapping ارث‌بری شده است).
    """

    __slots__ = ("_data",)

    def __init__(self, columns, values):
        self._data = dict(zip(columns, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def keys(self):
        return self._data.keys()

    def __repr__(self):  # pragma: no cover
        return f"<Row {self._data!r}>"


# ============================================================ SQL translation

_TYPE_MAP = {"TEXT": "NVARCHAR(MAX)", "INTEGER": "BIGINT", "REAL": "FLOAT", "BLOB": "VARBINARY(MAX)"}

_NOOP_PATTERNS = (
    re.compile(r"^\s*BEGIN\s*(IMMEDIATE|TRANSACTION)?\s*;?\s*$", re.IGNORECASE),
    re.compile(r"^\s*PRAGMA\s+foreign_keys\s*=\s*(ON|OFF)\s*;?\s*$", re.IGNORECASE),
)


def _split_top_level_commas(s: str):
    """جدا کردن رشته با کاما، بدون در نظر گرفتن کاماهایی داخل رشته یا پرانتز تودرتو."""
    parts, depth, cur, in_str = [], 0, "", False
    for ch in s:
        if ch == "'":
            in_str = not in_str
            cur += ch
        elif ch == "(" and not in_str:
            depth += 1
            cur += ch
        elif ch == ")" and not in_str:
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0 and not in_str:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _translate_upsert(sql: str):
    """
    ترجمه‌ی INSERT OR IGNORE / INSERT OR REPLACE / INSERT ... ON CONFLICT
    (سه الگوی مخصوص SQLite) به یک دستور MERGE معادل در T-SQL.
    ترتیب و تعداد پارامترهای «?» دقیقاً حفظ می‌شود؛ یعنی هیچ تغییری در
    کد پایتونی که پارامتر می‌فرستد لازم نیست.
    برمی‌گرداند: رشته‌ی SQL جدید، یا None اگر این یک upsert نبود.
    """
    m = re.match(
        r"^\s*INSERT\s+(?:OR\s+(IGNORE|REPLACE)\s+)?INTO\s+([\w.]+)\s*\(([^)]*)\)\s*"
        r"VALUES\s*\(([^)]*)\)\s*(.*)$",
        sql, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    or_mode = (m.group(1) or "").upper()
    table = m.group(2)
    cols = [c.strip() for c in m.group(3).split(",")]
    vals = _split_top_level_commas(m.group(4))
    tail = m.group(5).strip()

    conflict_cols = None
    update_cols = None

    cm = re.match(r"^ON\s+CONFLICT\s*\(([^)]*)\)\s*DO\s+UPDATE\s+SET\s+(.*)$", tail, re.IGNORECASE | re.DOTALL)
    if cm:
        conflict_cols = [c.strip() for c in cm.group(1).split(",")]
        update_cols = [part.split("=")[0].strip() for part in _split_top_level_commas(cm.group(2))]
    elif or_mode == "REPLACE":
        conflict_cols = [cols[0]]
        update_cols = [c for c in cols if c != cols[0]]
    elif or_mode == "IGNORE":
        conflict_cols = [cols[0]]
        update_cols = []
    else:
        return None  # INSERT معمولی؛ نیاز به ترجمه ندارد

    using_select = ", ".join(f"{v} AS [{c}]" for v, c in zip(vals, cols))
    on_clause = " AND ".join(f"target.[{c}] = src.[{c}]" for c in conflict_cols)
    merge_sql = (
        f"MERGE INTO {table} AS target "
        f"USING (SELECT {using_select}) AS src ({', '.join('[' + c + ']' for c in cols)}) "
        f"ON ({on_clause})"
    )
    if update_cols:
        set_clause = ", ".join(f"[{c}] = src.[{c}]" for c in update_cols)
        merge_sql += f" WHEN MATCHED THEN UPDATE SET {set_clause}"
    merge_sql += (
        f" WHEN NOT MATCHED THEN INSERT ({', '.join('[' + c + ']' for c in cols)}) "
        f"VALUES ({', '.join('src.[' + c + ']' for c in cols)});"
    )
    return merge_sql


def _translate_create_table_if_not_exists(sql: str):
    m = re.match(r"^\s*CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*)\)\s*;?\s*$", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    table, body = m.group(1), m.group(2)
    parts = _split_top_level_commas(body)

    # پاس اول: کدام ستون‌ها کلید اصلی هستند (باید طول محدود داشته باشند،
    # چون NVARCHAR(MAX) در SQL Server نمی‌تواند بخشی از PRIMARY KEY باشد)
    pk_cols = []
    for part in parts:
        pm = re.match(r"^(\w+)\s+\w+\b(.*)$", part.strip(), re.IGNORECASE)
        if pm and "PRIMARY KEY" in pm.group(2).upper():
            pk_cols.append(pm.group(1))

    new_cols = []
    for part in parts:
        pm = re.match(r"^(\w+)\s+(TEXT|INTEGER|REAL|BLOB)\b(.*)$", part.strip(), re.IGNORECASE)
        if pm:
            colname, coltype, rest = pm.groups()
            is_pk = colname in pk_cols
            if coltype.upper() == "TEXT" and is_pk:
                mapped = "NVARCHAR(255)"
            else:
                mapped = _TYPE_MAP[coltype.upper()]
            new_cols.append(f"[{colname}] {mapped}" + (" NOT NULL" if is_pk else ""))
        else:
            new_cols.append(part.strip())
    pk_clause = f", PRIMARY KEY ({', '.join('[' + c + ']' for c in pk_cols)})" if pk_cols else ""
    return (
        f"IF OBJECT_ID('dbo.{table}', 'U') IS NULL BEGIN "
        f"CREATE TABLE {table} ({', '.join(new_cols)}{pk_clause}) END"
    )


def _translate_add_column(sql: str):
    m = re.match(r"^\s*ALTER TABLE\s+(\w+)\s+ADD COLUMN\s+(\w+)\s+(TEXT|INTEGER|REAL|BLOB)\s*;?\s*$",
                 sql, re.IGNORECASE)
    if not m:
        return None
    table, col, coltype = m.groups()
    return f"ALTER TABLE {table} ADD [{col}] {_TYPE_MAP[coltype.upper()]}"


def _translate_create_unique_index(sql: str):
    m = re.match(r"^\s*CREATE UNIQUE INDEX IF NOT EXISTS\s+(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)\s*;?\s*$",
                 sql, re.IGNORECASE)
    if not m:
        return None
    idx, table, cols = m.groups()
    return (
        f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='{idx}' "
        f"AND object_id = OBJECT_ID('dbo.{table}')) "
        f"CREATE UNIQUE INDEX {idx} ON {table}({cols})"
    )


def _translate_pragma_table_info(sql: str):
    m = re.match(r"^\s*PRAGMA\s+table_info\((\w+)\)\s*;?\s*$", sql, re.IGNORECASE)
    if not m:
        return None
    table = m.group(1)
    return (
        "SELECT ORDINAL_POSITION - 1 AS cid, COLUMN_NAME AS name, DATA_TYPE AS type, "
        "CASE WHEN IS_NULLABLE = 'NO' THEN 1 ELSE 0 END AS notnull, "
        "COLUMN_DEFAULT AS dflt_value, 0 AS pk "
        f"FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table}' "
        "ORDER BY ORDINAL_POSITION"
    )


def translate_sql(sql: str):
    """
    رشته‌ی SQL ورودی (به سبک SQLite) را می‌گیرد و رشته‌ی T-SQL معادل
    را برمی‌گرداند. اگر دستور باید کاملاً نادیده گرفته شود (مثل
    BEGIN IMMEDIATE یا PRAGMA foreign_keys) رشته‌ی خالی برمی‌گرداند.
    """
    stripped = sql.strip()

    for pat in _NOOP_PATTERNS:
        if pat.match(stripped):
            return ""

    for fn in (
        _translate_create_table_if_not_exists,
        _translate_add_column,
        _translate_create_unique_index,
        _translate_pragma_table_info,
        _translate_upsert,
    ):
        out = fn(stripped)
        if out is not None:
            stripped = out
            break

    # واژه‌ی "key" در SQL Server کلمه‌ی رزرو شده است؛ هرجا به‌عنوان نام
    # ستون (نه داخل PRIMARY KEY و نه از قبل داخل []) ظاهر شود باید با
    # [key] نوشته شود.
    stripped = re.sub(r"(?<!\[)\bkey\b(?!\])", "[key]", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"PRIMARY\s+\[key\]", "PRIMARY KEY", stripped, flags=re.IGNORECASE)

    # GLOB '[0-9]*'  ->  LIKE '[0-9]%'  (شروع رشته با یک رقم)
    stripped = re.sub(r"(\S+)\s+GLOB\s+'\[0-9\]\*'", r"\1 LIKE '[0-9]%'", stripped, flags=re.IGNORECASE)

    # CAST(x AS INTEGER/REAL) -> TRY_CAST(x AS INT/FLOAT)  (بدون خطا در تبدیل ناموفق)
    stripped = re.sub(r"\bCAST\(", "TRY_CAST(", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bAS\s+INTEGER\)", "AS INT)", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bAS\s+REAL\)", "AS FLOAT)", stripped, flags=re.IGNORECASE)

    # ORDER BY ... LIMIT n   ->   ORDER BY ... OFFSET 0 ROWS FETCH NEXT n ROWS ONLY
    stripped = re.sub(
        r"ORDER BY\s+(.+?)\s+LIMIT\s+(\d+)\s*;?\s*$",
        lambda mm: f"ORDER BY {mm.group(1)} OFFSET 0 ROWS FETCH NEXT {mm.group(2)} ROWS ONLY",
        stripped, flags=re.IGNORECASE | re.DOTALL,
    )

    return stripped


# ============================================================ Cursor/Connection

class CursorResult:
    def __init__(self, raw_cursor, columns, lastrowid):
        self._cursor = raw_cursor
        self._columns = columns
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return Row(self._columns, list(row))

    def fetchall(self):
        return [Row(self._columns, list(r)) for r in self._cursor.fetchall()]

    def fetchmany(self, size=1):
        return [Row(self._columns, list(r)) for r in self._cursor.fetchmany(size)]

    def __iter__(self):
        for r in self._cursor.fetchall():
            yield Row(self._columns, list(r))


class Connection:
    """پوشش (wrapper) روی pyodbc.Connection تا رفتار شبیه sqlite3.Connection داشته باشد."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def execute(self, sql, params=()):
        translated = translate_sql(sql)
        cur = self._conn.cursor()
        if translated == "":
            # دستور کاملاً بی‌اثر (BEGIN IMMEDIATE / PRAGMA و ...)
            return CursorResult(cur, None, None)

        if params:
            cur.execute(translated, tuple(params))
        else:
            cur.execute(translated)

        columns = [d[0] for d in cur.description] if cur.description else None

        lastrowid = None
        if re.match(r"^\s*(INSERT|MERGE)\b", translated, re.IGNORECASE):
            try:
                idcur = self._conn.cursor()
                idcur.execute("SELECT CAST(SCOPE_IDENTITY() AS BIGINT)")
                idrow = idcur.fetchone()
                lastrowid = int(idrow[0]) if idrow and idrow[0] is not None else None
                idcur.close()
            except Exception:
                lastrowid = None

        return CursorResult(cur, columns, lastrowid)

    def executescript(self, script):
        for stmt in script.split(";"):
            if stmt.strip():
                self.execute(stmt)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


# ================================================================== schema

# همان جدول‌های نسخه‌ی SQLite قبلی، این‌بار با نوع‌های SQL Server.
# هر جدول با IF OBJECT_ID(...) IS NULL محافظت می‌شود تا اجرای دوباره
# مشکلی ایجاد نکند (idempotent).

_TABLES = {
    "dastgahjadid": """
        [cod] NVARCHAR(255) NOT NULL PRIMARY KEY,
        [name] NVARCHAR(MAX) NOT NULL,
        [hadaftedadkharabi] FLOAT DEFAULT 0,
        [pazireshtedadkharabi] FLOAT DEFAULT 0,
        [hadafzamantavaghof] FLOAT DEFAULT 0,
        [pazireshzamantavaghof] FLOAT DEFAULT 0
    """,
    "mojryjadid": """
        [cod] BIGINT NOT NULL PRIMARY KEY,
        [name] NVARCHAR(MAX) NOT NULL
    """,
    "kalajadid": """
        [cod] NVARCHAR(255) NOT NULL PRIMARY KEY,
        [name] NVARCHAR(MAX) NOT NULL,
        [vahed] NVARCHAR(MAX)
    """,
    "data": """
        [id] INT IDENTITY(1,1) PRIMARY KEY,
        [shomare_darkhast] BIGINT,
        [etefaghi] BIGINT DEFAULT 0,
        [pishgirane] BIGINT DEFAULT 0,
        [asasy] BIGINT DEFAULT 0,
        [tekrary] BIGINT DEFAULT 0,
        [sayer] BIGINT DEFAULT 0,
        [namdastgah] NVARCHAR(MAX),
        [codedastgah] NVARCHAR(MAX),
        [sharhenaghs] NVARCHAR(MAX),
        [barghi] BIGINT DEFAULT 0,
        [mekanik] BIGINT DEFAULT 0,
        [abzarsazi] BIGINT DEFAULT 0,
        [taminghate] BIGINT DEFAULT 0,
        [kontrol] BIGINT DEFAULT 0,
        [tasisat] BIGINT DEFAULT 0,
        [tolid] BIGINT DEFAULT 0,
        [sayertakhir] BIGINT DEFAULT 0,
        [darkhastkonande] NVARCHAR(MAX),
        [sharhekareanjamshode] NVARCHAR(MAX),
        [tarikhdarkhast] NVARCHAR(MAX),
        [timedarkhast] NVARCHAR(MAX),
        [tarikhstart] NVARCHAR(MAX),
        [timestart] NVARCHAR(MAX),
        [tarikhend] NVARCHAR(MAX),
        [timeEnd] NVARCHAR(MAX),
        [timetavaghofdastgah] NVARCHAR(MAX),
        [tozihat] NVARCHAR(MAX)
    """,
    "mojry": """
        [id] INT IDENTITY(1,1) PRIMARY KEY,
        [kod_mojri] BIGINT,
        [nam_mojri] NVARCHAR(MAX),
        [shomare_darkhast] BIGINT,
        [tarikh] NVARCHAR(MAX),
        [saat] NVARCHAR(MAX),
        [kod_dastgah] NVARCHAR(MAX)
    """,
    "mvademasrafi": """
        [id] INT IDENTITY(1,1) PRIMARY KEY,
        [code] NVARCHAR(MAX),
        [name] NVARCHAR(MAX),
        [qty] FLOAT,
        [vahed] NVARCHAR(MAX),
        [shomare_darkhast] BIGINT,
        [kod_dastgah] NVARCHAR(MAX),
        [tarikh] NVARCHAR(MAX)
    """,
    "users": """
        [id] INT IDENTITY(1,1) PRIMARY KEY,
        [username] NVARCHAR(255) NOT NULL UNIQUE,
        [password_hash] NVARCHAR(MAX) NOT NULL,
        [full_name] NVARCHAR(MAX),
        [role] NVARCHAR(50) NOT NULL DEFAULT 'viewer',
        [is_active] BIGINT NOT NULL DEFAULT 1,
        [created_at] NVARCHAR(MAX)
    """,
    "audit_log": """
        [id] INT IDENTITY(1,1) PRIMARY KEY,
        [user_id] BIGINT,
        [username] NVARCHAR(MAX),
        [action] NVARCHAR(MAX) NOT NULL,
        [event_time] NVARCHAR(MAX) NOT NULL,
        [ip_address] NVARCHAR(MAX),
        [user_agent] NVARCHAR(MAX)
    """,
    "bazdid_rozane": """
        [id] INT IDENTITY(1,1) PRIMARY KEY,
        [kod_dastgah] NVARCHAR(MAX),
        [nam_dastgah] NVARCHAR(MAX),
        [tarikh] NVARCHAR(MAX),
        [ravankari] BIGINT DEFAULT 0,
        [seday_ghyrmoadi] BIGINT DEFAULT 0,
        [nashti] BIGINT DEFAULT 0,
        [hefazha_imeni] BIGINT DEFAULT 0,
        [sim_keshi_bargh] BIGINT DEFAULT 0,
        [tamizi_mohit] BIGINT DEFAULT 0,
        [feshar_hava_roghan] BIGINT DEFAULT 0,
        [stop_ezterari] BIGINT DEFAULT 0,
        [abzar_janebi] BIGINT DEFAULT 0,
        [damaye_dastgah] BIGINT DEFAULT 0,
        [bazresh_konande] NVARCHAR(MAX),
        [tozihat] NVARCHAR(MAX),
        [created_at] NVARCHAR(MAX)
    """,
    "bazdid_pishgirane": """
        [id] INT IDENTITY(1,1) PRIMARY KEY,
        [kod_dastgah] NVARCHAR(MAX),
        [nam_dastgah] NVARCHAR(MAX),
        [tarikh] NVARCHAR(MAX),
        [noe_bazdid] NVARCHAR(MAX),
        [bearing_motor] BIGINT DEFAULT 0,
        [tasme_coupling] BIGINT DEFAULT 0,
        [filter_roghan] BIGINT DEFAULT 0,
        [filter_hava] BIGINT DEFAULT 0,
        [larzesh_motor] BIGINT DEFAULT 0,
        [damaye_motor] BIGINT DEFAULT 0,
        [ettesalat_bargh] BIGINT DEFAULT 0,
        [roghan_gearbox] BIGINT DEFAULT 0,
        [sistem_hydrolic] BIGINT DEFAULT 0,
        [calibration_sensor] BIGINT DEFAULT 0,
        [limit_switch_imeni] BIGINT DEFAULT 0,
        [zanjir_tasme_naghale] BIGINT DEFAULT 0,
        [tamizkari_gireskari] BIGINT DEFAULT 0,
        [panel_bargh_control] BIGINT DEFAULT 0,
        [vaziat_kolli] NVARCHAR(MAX),
        [tarikh_bazdid_badi] NVARCHAR(MAX),
        [bazresh_konande] NVARCHAR(MAX),
        [tozihat] NVARCHAR(MAX),
        [created_at] NVARCHAR(MAX)
    """,
    "key_equipment": """
        [cod] NVARCHAR(255) NOT NULL PRIMARY KEY,
        [name] NVARCHAR(MAX) NOT NULL,
        [linked_device_cod] NVARCHAR(MAX),
        [machine_count] NVARCHAR(MAX),
        [bottleneck] NVARCHAR(MAX),
        [product_count] NVARCHAR(MAX),
        [shift_work] NVARCHAR(MAX),
        [mtbf] NVARCHAR(MAX),
        [external_parts] NVARCHAR(MAX),
        [downtime_hours] NVARCHAR(MAX),
        [machine_age] NVARCHAR(MAX),
        [spare_parts] NVARCHAR(MAX),
        [repeated_stops] NVARCHAR(MAX),
        [customer_impact] NVARCHAR(MAX),
        [quality_impact] NVARCHAR(MAX),
        [score] NVARCHAR(MAX),
        [classification] NVARCHAR(MAX),
        [substitute_codes] NVARCHAR(MAX),
        [substitute_names] NVARCHAR(MAX),
        [contractor_alternative] NVARCHAR(MAX),
        [manual_fields] NVARCHAR(MAX) DEFAULT '',
        [updated_at] NVARCHAR(MAX)
    """,
    "key_equipment_meta": "[key] NVARCHAR(255) NOT NULL PRIMARY KEY, [value] NVARCHAR(MAX)",
    "monthly_repair_cost": """
        [jalali_year] BIGINT NOT NULL,
        [jalali_month] BIGINT NOT NULL,
        [amount] FLOAT NOT NULL DEFAULT 0,
        [updated_by] NVARCHAR(MAX),
        [updated_at] NVARCHAR(MAX),
        PRIMARY KEY ([jalali_year], [jalali_month])
    """,
    "machine_passport": """
        [device_cod] NVARCHAR(255) NOT NULL PRIMARY KEY,
        [device_name] NVARCHAR(MAX),
        [source_name] NVARCHAR(MAX),
        [source_cod] NVARCHAR(MAX),
        [manufacturer_country] NVARCHAR(MAX),
        [manufacturer_company] NVARCHAR(MAX),
        [useful_life] NVARCHAR(MAX),
        [manufacture_date] NVARCHAR(MAX),
        [serial_number] NVARCHAR(MAX),
        [commissioning_date] NVARCHAR(MAX),
        [purchase_condition] NVARCHAR(MAX),
        [technical_info] NVARCHAR(MAX),
        [energy_consumption] NVARCHAR(MAX),
        [other_energy] NVARCHAR(MAX),
        [cooling_system] NVARCHAR(MAX),
        [dimensions_length] NVARCHAR(MAX),
        [dimensions_width] NVARCHAR(MAX),
        [dimensions_height] NVARCHAR(MAX),
        [accessories] NVARCHAR(MAX),
        [operation_description] NVARCHAR(MAX),
        [notes] NVARCHAR(MAX),
        [updated_at] NVARCHAR(MAX)
    """,
    "machine_product_usage": """
        [device_cod] NVARCHAR(255) NOT NULL PRIMARY KEY,
        [product_flags] NVARCHAR(MAX) DEFAULT '',
        [updated_at] NVARCHAR(MAX)
    """,
    "machine_passport_meta": "[key] NVARCHAR(255) NOT NULL PRIMARY KEY, [value] NVARCHAR(MAX)",
}

# ترتیب مهم است: جدول‌های مرجع قبل از جدول‌هایی که (منطقاً) به آن‌ها
# ارجاع می‌دهند ساخته می‌شوند.
_TABLE_ORDER = [
    "dastgahjadid", "mojryjadid", "kalajadid", "data", "mojry", "mvademasrafi",
    "users", "audit_log", "bazdid_rozane", "bazdid_pishgirane",
    "key_equipment", "key_equipment_meta", "monthly_repair_cost",
    "machine_passport", "machine_product_usage", "machine_passport_meta",
]


def _ensure_schema(conn: Connection) -> None:
    for name in _TABLE_ORDER:
        body = _TABLES[name]
        conn.execute(f"IF OBJECT_ID('dbo.{name}', 'U') IS NULL BEGIN CREATE TABLE {name} ({body}) END")
    conn.commit()


def _column_exists(conn: Connection, table: str, column: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
        (table, column),
    ).fetchone()
    return row is not None


def _migrate_status_column(conn: Connection) -> None:
    """
    ستون‌های گردش کار درخواست‌ها را برای مرحله‌ی «در انتظار / در حال بررسی /
    تکمیل شده» اضافه می‌کند و ستون وضعیت عملیاتی دستگاه را نیز برای ثبت
    وضعیت لحظه‌ای خرابی اضافه می‌کند.
    """
    if not _column_exists(conn, "data", "status"):
        conn.execute("ALTER TABLE data ADD [status] NVARCHAR(50)")
        conn.execute("UPDATE data SET status = 'completed' WHERE status IS NULL")
        conn.commit()

    if not _column_exists(conn, "data", "device_operational_status"):
        conn.execute("ALTER TABLE data ADD [device_operational_status] NVARCHAR(50) NULL")
        conn.commit()

    # قفل بررسی و تکمیل: شناسه‌ی نیرویی که درخواست را باز کرده و زمان قفل.
    # این ستون‌ها باعث می‌شوند قفل در خود SQL Server ثبت شود و بین چند
    # کاربر/چند worker برنامه مشترک و قابل اتکا باشد.
    if not _column_exists(conn, "data", "review_locked_by"):
        conn.execute("ALTER TABLE data ADD [review_locked_by] INT NULL")
        conn.commit()

    if not _column_exists(conn, "data", "review_locked_at"):
        conn.execute("ALTER TABLE data ADD [review_locked_at] NVARCHAR(50) NULL")
        conn.commit()


def _migrate_request_number(conn: Connection) -> None:
    conn.execute("UPDATE data SET shomare_darkhast = id WHERE shomare_darkhast IS NULL")
    conn.commit()
    exists = conn.execute(
        "SELECT 1 FROM sys.indexes WHERE name='ux_data_shomare_darkhast' "
        "AND object_id = OBJECT_ID('dbo.data')"
    ).fetchone()
    if not exists:
        conn.execute("CREATE UNIQUE INDEX ux_data_shomare_darkhast ON data(shomare_darkhast)")
    conn.commit()


def _ensure_default_constraint(conn: Connection, table: str, column: str, default_sql: str, constraint_name: str) -> None:
    """
    اگر ستون NOT NULL باشد ولی مقدار پیش‌فرض (DEFAULT) نداشته باشد، درجش
    می‌کند. این برای رفع یک اشکال در نسخه‌ی اولیه‌ی اسکریپت مهاجرت است
    که مقدار DEFAULT چند ستون (مثل users.is_active) از قلم افتاده بود و
    باعث خطای «Cannot insert the value NULL» می‌شد وقتی کد آن ستون را
    در INSERT ذکر نمی‌کرد (و به‌درستی به DEFAULT تکیه می‌کرد).
    """
    exists = conn.execute(
        "SELECT 1 FROM sys.default_constraints dc "
        "JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id "
        "WHERE dc.parent_object_id = OBJECT_ID(?) AND c.name = ?",
        (f"dbo.{table}", column),
    ).fetchone()
    if not exists:
        conn.execute(
            f"ALTER TABLE dbo.{table} ADD CONSTRAINT {constraint_name} DEFAULT {default_sql} FOR [{column}]"
        )
        conn.commit()


def _migrate_missing_defaults(conn: Connection) -> None:
    _ensure_default_constraint(conn, "users", "is_active", "1", "DF_users_is_active")
    _ensure_default_constraint(conn, "users", "role", "'viewer'", "DF_users_role")
    _ensure_default_constraint(conn, "monthly_repair_cost", "amount", "0", "DF_monthly_repair_cost_amount")


def get_connection(database_name: str = None) -> Connection:
    raw = pyodbc.connect(_build_connection_string(database_name), autocommit=False)
    conn = Connection(raw)
    _ensure_schema(conn)
    _migrate_status_column(conn)
    _migrate_request_number(conn)
    _migrate_missing_defaults(conn)
    return conn

