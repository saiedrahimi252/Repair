# -*- coding: utf-8 -*-
"""
اسکریپت انتقال داده‌های قدیمی (اکسپورت شده از Access) به دیتابیس SQLite.

این اسکریپت یک‌بار مصرف است؛ فایل‌های اکسل اکسپورت‌شده را می‌خواند و در
دیتابیس repair.db (نسخه‌ی وب) درج می‌کند. ترتیب درج مهم است چون جدول‌های
مرجع (دستگاه، کالا، مجری) باید قبل از جدول‌هایی که به آن‌ها اشاره
می‌کنند پر شوند.
"""

import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from database import get_connection  # noqa: E402

UPLOADS = Path("/mnt/user-data/uploads")


def load_rows(filename):
    wb = openpyxl.load_workbook(UPLOADS / filename, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data_rows = [r for r in rows[1:] if any(c is not None for c in r)]
    return header, data_rows


def to_flag(v):
    """True/False/None/عدد -> 0 یا 1"""
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    try:
        return 1 if int(v) else 0
    except (TypeError, ValueError):
        return 0


def to_text(v):
    if v is None:
        return None
    return str(v)


def main():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = OFF")  # داده‌های قدیمی ممکن است ارجاع‌های یتیم داشته باشند

    # ---------------------------------------------------------- dastgahjadid
    header, rows = load_rows("dastgahjadid.xlsx")
    idx = {h: i for i, h in enumerate(header)}
    count = 0
    for r in rows:
        conn.execute(
            """INSERT INTO dastgahjadid (cod, name, hadaftedadkharabi, pazireshtedadkharabi,
                                          hadafzamantavaghof, pazireshzamantavaghof)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(cod) DO UPDATE SET
                 name=excluded.name, hadaftedadkharabi=excluded.hadaftedadkharabi,
                 pazireshtedadkharabi=excluded.pazireshtedadkharabi,
                 hadafzamantavaghof=excluded.hadafzamantavaghof,
                 pazireshzamantavaghof=excluded.pazireshzamantavaghof""",
            (
                to_text(r[idx["cod"]]), to_text(r[idx["name"]]),
                r[idx["hadaftedadkharabi"]] or 0, r[idx["pazireshtedadkharabi"]] or 0,
                r[idx["hadafzamantavaghof"]] or 0, r[idx["pazireshzamantavaghof"]] or 0,
            ),
        )
        count += 1
    print(f"dastgahjadid: {count} رکورد وارد شد")

    # -------------------------------------------------------------- kalajadid
    header, rows = load_rows("kalajadid.xlsx")
    idx = {h: i for i, h in enumerate(header)}
    count = 0
    for r in rows:
        conn.execute(
            """INSERT INTO kalajadid (cod, name, vahed) VALUES (?,?,?)
               ON CONFLICT(cod) DO UPDATE SET name=excluded.name, vahed=excluded.vahed""",
            (to_text(r[idx["cod"]]), to_text(r[idx["name"]]), to_text(r[idx["vahed"]])),
        )
        count += 1
    print(f"kalajadid: {count} رکورد وارد شد")

    # ------------------------------------------------------------- mojryjadid
    header, rows = load_rows("mojryjadid.xlsx")
    idx = {h: i for i, h in enumerate(header)}
    count = 0
    for r in rows:
        conn.execute(
            """INSERT INTO mojryjadid (cod, name) VALUES (?,?)
               ON CONFLICT(cod) DO UPDATE SET name=excluded.name""",
            (int(r[idx["cod"]]), to_text(r[idx["name"]])),
        )
        count += 1
    print(f"mojryjadid: {count} رکورد وارد شد")

    conn.commit()  # جدول‌های مرجع را قطعی می‌کنیم قبل از جدول‌های وابسته

    # -------------------------------------------------------------------- data
    # ستون id در SQL Server از نوع IDENTITY است؛ برای درج مقدار صریح id
    # (همان idهای قدیمی) باید موقتاً IDENTITY_INSERT را روشن کنیم.
    header, rows = load_rows("data.xlsx")
    idx = {h: i for i, h in enumerate(header)}
    count = 0
    conn.execute("SET IDENTITY_INSERT dbo.data ON")
    for r in rows:
        conn.execute(
            """INSERT INTO data (
                id, etefaghi, pishgirane, asasy, tekrary, sayer,
                namdastgah, codedastgah, sharhenaghs,
                barghi, mekanik, abzarsazi, taminghate, kontrol, tasisat, tolid, sayertakhir,
                darkhastkonande, sharhekareanjamshode,
                tarikhdarkhast, timedarkhast, tarikhstart, timestart, tarikhend, timeEnd,
                timetavaghofdastgah, tozihat
            ) VALUES (?,?,?,?,?,?, ?,?,?, ?,?,?,?,?,?,?,?, ?,?, ?,?,?,?,?,?, ?,?)
            ON CONFLICT(id) DO UPDATE SET
                etefaghi=excluded.etefaghi, pishgirane=excluded.pishgirane, asasy=excluded.asasy,
                tekrary=excluded.tekrary, sayer=excluded.sayer,
                namdastgah=excluded.namdastgah, codedastgah=excluded.codedastgah, sharhenaghs=excluded.sharhenaghs,
                barghi=excluded.barghi, mekanik=excluded.mekanik, abzarsazi=excluded.abzarsazi,
                taminghate=excluded.taminghate, kontrol=excluded.kontrol, tasisat=excluded.tasisat,
                tolid=excluded.tolid, sayertakhir=excluded.sayertakhir,
                darkhastkonande=excluded.darkhastkonande, sharhekareanjamshode=excluded.sharhekareanjamshode,
                tarikhdarkhast=excluded.tarikhdarkhast, timedarkhast=excluded.timedarkhast,
                tarikhstart=excluded.tarikhstart, timestart=excluded.timestart,
                tarikhend=excluded.tarikhend, timeEnd=excluded.timeEnd,
                timetavaghofdastgah=excluded.timetavaghofdastgah, tozihat=excluded.tozihat""",
            (
                int(r[idx["id"]]),
                to_flag(r[idx["etefaghi"]]), to_flag(r[idx["pishgirane"]]), to_flag(r[idx["asasy"]]),
                to_flag(r[idx["tekrary"]]), to_flag(r[idx["sayer"]]),
                to_text(r[idx["namdastgah"]]), to_text(r[idx["codedastgah"]]), to_text(r[idx["sharhenaghs"]]),
                to_flag(r[idx["barghi"]]), to_flag(r[idx["mekanik"]]), to_flag(r[idx["abzarsazi"]]),
                to_flag(r[idx["taminghate"]]), to_flag(r[idx["kontrol"]]), to_flag(r[idx["tasisat"]]),
                to_flag(r[idx["tolid"]]), to_flag(r[idx["sayertakhir"]]),
                to_text(r[idx["darkhastkonande"]]), to_text(r[idx["sharhekareanjamshode"]]),
                to_text(r[idx["tarikhdarkhast"]]), to_text(r[idx["timedarkhast"]]),
                to_text(r[idx["tarikhstart"]]), to_text(r[idx["timestart"]]),
                to_text(r[idx["tarikhend"]]), to_text(r[idx["timeEnd"]]),
                to_text(r[idx["timetavaghofdastgah"]]), to_text(r[idx["tozihat"]]),
            ),
        )
        count += 1
    conn.execute("SET IDENTITY_INSERT dbo.data OFF")
    print(f"data: {count} رکورد وارد شد")

    # -------------------------------------------------------------------- mojry
    header, rows = load_rows("mojry.xlsx")
    idx = {h: i for i, h in enumerate(header)}
    count = 0
    for r in rows:
        conn.execute(
            """INSERT INTO mojry (kod_mojri, nam_mojri, shomare_darkhast, tarikh, saat, kod_dastgah)
               VALUES (?,?,?,?,?,?)""",
            (
                int(r[idx["id"]]) if r[idx["id"]] is not None else None,
                to_text(r[idx["name"]]),
                int(r[idx["shomareh darkhast"]]) if r[idx["shomareh darkhast"]] is not None else None,
                to_text(r[idx["tarikh"]]), to_text(r[idx["time"]]), to_text(r[idx["kodedastgah"]]),
            ),
        )
        count += 1
    print(f"mojry: {count} رکورد وارد شد")

    # -------------------------------------------------------------- mvademasrafi
    header, rows = load_rows("mvademasrafi.xlsx")
    idx = {h: i for i, h in enumerate(header)}
    count = 0
    for r in rows:
        conn.execute(
            """INSERT INTO mvademasrafi (code, name, qty, vahed, shomare_darkhast, kod_dastgah, tarikh)
               VALUES (?,?,?,?,?,?,?)""",
            (
                to_text(r[idx["id"]]), to_text(r[idx["name"]]), r[idx["tedad"]], to_text(r[idx["vahed"]]),
                int(r[idx["shomarehdarkhast1"]]) if r[idx["shomarehdarkhast1"]] is not None else None,
                to_text(r[idx["codedastgah2"]]), to_text(r[idx["tarikh"]]),
            ),
        )
        count += 1
    print(f"mvademasrafi: {count} رکورد وارد شد")

    conn.commit()
    conn.close()
    print("انتقال داده با موفقیت انجام شد.")


if __name__ == "__main__":
    main()
