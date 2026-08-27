from __future__ import annotations

from datetime import date, datetime, timedelta
from dataclasses import dataclass, asdict
import re
import unicodedata

from .materials_1c import read_first_sheet_xlsx, read_csv, ImportFormatError

FIELD_ALIASES = {
    "code": ("код изделия", "код", "артикул", "позиция"),
    "client": ("клиент", "контрагент", "заказчик"),
    "order_ref": ("заказ", "номер заказа", "№ заказа", "заказ №"),
    "product_type": ("тип", "тип изделия", "конструкция"),
    "length_mm": ("l, мм", "l", "длина изделия, мм", "длина изделия"),
    "width_mm": ("b, мм", "b", "ширина изделия, мм", "ширина изделия"),
    "height_mm": ("h, мм", "h", "высота изделия, мм", "высота изделия"),
    "blank_length_mm": ("длина заготовки, мм", "длина заготовки", "заготовка длина"),
    "blank_width_mm": ("ширина заготовки, мм", "ширина заготовки", "заготовка ширина"),
    "quantity": ("количество", "кол-во", "тираж", "шт"),
    "required_board_grade": ("марка", "марка картона", "требуемая марка"),
    "profile": ("профиль", "гофра", "профиль гофры"),
    "colors": ("цветов", "цвета", "красок", "количество цветов"),
    "die_cut": ("штанцформа", "штанцовка", "высечка"),
    "due_date": ("срок", "дата", "срок исполнения", "дата исполнения"),
}

PROFILES = {"E", "B", "C", "BE", "CE", "BC"}


def _norm(v: object) -> str:
    s = "" if v is None else str(v)
    s = unicodedata.normalize("NFKC", s).strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", s)


def _num(v: object | None) -> float | None:
    if v is None or v == "": return None
    if isinstance(v, (int, float)) and not isinstance(v, bool): return float(v)
    s = str(v).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s: return None
    try: return float(s)
    except ValueError: return None


def _date(v: object | None) -> str | None:
    if v in (None, ""): return None
    if isinstance(v, datetime): return v.date().isoformat()
    if isinstance(v, date): return v.isoformat()
    if isinstance(v, (int, float)) and 1 <= float(v) <= 100000:
        try: return (date(1899, 12, 30) + timedelta(days=int(float(v)))).isoformat()
        except OverflowError: pass
    s = str(v).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try: return datetime.strptime(s, fmt).date().isoformat()
        except ValueError: pass
    return s


def _bool(v: object | None) -> bool:
    return _norm(v) in {"да", "yes", "true", "1", "есть", "+"}


def _ptype(v: object | None) -> str:
    s = _norm(v)
    if s in {"", "0201", "fefco 0201", "fefco0201", "ящик", "гофроящик"}: return "0201"
    if s in {"лист", "sheet", "заготовка", "blank"}: return "sheet"
    return s


def _header(rows: list[list[object | None]]) -> tuple[int, dict[int, str]]:
    aliases = {}
    for field, vals in FIELD_ALIASES.items():
        for x in vals: aliases[_norm(x)] = field
    best = None
    for ri, row in enumerate(rows[:20]):
        m = {ci: aliases[_norm(v)] for ci, v in enumerate(row) if _norm(v) in aliases}
        if best is None or len(m) > len(best[1]): best = (ri, m)
    if best is None or len(best[1]) < 6:
        raise ImportFormatError("Не найден заголовок шаблона изделий. Используйте шаблон KE | BOX CALC v0.7.")
    return best


def _validate(d: dict, row_no: int) -> list[dict]:
    issues = []
    def err(field, msg): issues.append({"row_number": row_no, "field": field, "message": msg})
    if not d.get("code"): d["code"] = f"ITEM-{row_no}"
    if d["quantity"] is None or d["quantity"] <= 0 or int(d["quantity"]) != d["quantity"]: err("quantity", "Количество должно быть целым числом больше 0")
    if not d.get("required_board_grade"): err("required_board_grade", "Не указана марка картона")
    if not d.get("profile"): err("profile", "Не указан профиль")
    elif d["profile"] not in PROFILES: err("profile", "Допустимые профили: E, B, C, BE, CE, BC")
    if d["product_type"] == "0201":
        for f, label in (("length_mm","L"),("width_mm","B"),("height_mm","H")):
            if d.get(f) is None or d[f] <= 0: err(f, f"Для FEFCO 0201 нужен размер {label}")
    elif d["product_type"] == "sheet":
        for f, label in (("blank_length_mm","длина заготовки"),("blank_width_mm","ширина заготовки")):
            if d.get(f) is None or d[f] <= 0: err(f, f"Для листа нужна {label}")
    else:
        err("product_type", "Поддерживаются только FEFCO 0201 и Лист")
    return issues


def parse_order_import(content: bytes, filename: str) -> dict:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        rows = read_first_sheet_xlsx(content)
    elif lower.endswith(".csv"):
        rows = read_csv(content)
    else:
        raise ImportFormatError("Поддерживаются файлы XLSX и CSV")
    hi, mapping = _header(rows)
    out, issues = [], []
    for ridx, row in enumerate(rows[hi+1:], start=hi+2):
        if not any(v not in (None, "") for v in row): continue
        raw = {field: (row[ci] if ci < len(row) else None) for ci, field in mapping.items()}
        d = {
            "row_number": ridx,
            "code": str(raw.get("code") or "").strip(),
            "client": str(raw.get("client") or "").strip() or None,
            "order_ref": str(raw.get("order_ref") or "").strip() or None,
            "product_type": _ptype(raw.get("product_type")),
            "length_mm": _num(raw.get("length_mm")),
            "width_mm": _num(raw.get("width_mm")),
            "height_mm": _num(raw.get("height_mm")),
            "blank_length_mm": _num(raw.get("blank_length_mm")),
            "blank_width_mm": _num(raw.get("blank_width_mm")),
            "quantity": _num(raw.get("quantity")),
            "required_board_grade": str(raw.get("required_board_grade") or "").strip().upper(),
            "profile": str(raw.get("profile") or "").strip().upper(),
            "colors": int(_num(raw.get("colors")) or 1),
            "die_cut": _bool(raw.get("die_cut")),
            "due_date": _date(raw.get("due_date")),
        }
        row_issues = _validate(d, ridx)
        d["quantity"] = int(d["quantity"]) if d["quantity"] is not None and int(d["quantity"]) == d["quantity"] else d["quantity"]
        d["valid"] = not row_issues
        d["issues"] = row_issues
        out.append(d)
        issues.extend(row_issues)
    return {
        "file_name": filename,
        "rows": out,
        "stats": {
            "rows_total": len(out),
            "rows_valid": sum(1 for x in out if x["valid"]),
            "rows_invalid": sum(1 for x in out if not x["valid"]),
            "issues": len(issues),
        },
        "issues": issues,
    }


def validate_order_rows(rows: list[dict]) -> dict:
    out, issues = [], []
    for idx, src in enumerate(rows, start=1):
        d = dict(src)
        row_no = int(d.get("row_number") or idx + 1)
        d["product_type"] = _ptype(d.get("product_type"))
        for f in ("length_mm","width_mm","height_mm","blank_length_mm","blank_width_mm","quantity"):
            d[f] = _num(d.get(f))
        d["profile"] = str(d.get("profile") or "").strip().upper()
        d["required_board_grade"] = str(d.get("required_board_grade") or "").strip().upper()
        d["colors"] = int(_num(d.get("colors")) or 1)
        d["die_cut"] = _bool(d.get("die_cut")) if not isinstance(d.get("die_cut"), bool) else d["die_cut"]
        row_issues = _validate(d, row_no)
        if d["quantity"] is not None and int(d["quantity"]) == d["quantity"]: d["quantity"] = int(d["quantity"])
        d["valid"] = not row_issues
        d["issues"] = row_issues
        out.append(d); issues.extend(row_issues)
    return {"rows": out, "stats": {"rows_total": len(out), "rows_valid": sum(x["valid"] for x in out), "rows_invalid": sum(not x["valid"] for x in out), "issues": len(issues)}, "issues": issues}
