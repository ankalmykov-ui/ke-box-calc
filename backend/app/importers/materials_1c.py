from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import PurePosixPath
import csv
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "code_1c": ("код 1с", "код", "код номенклатуры", "код_1с", "код номенклатуры 1с"),
    "variant_1c": ("характеристика 1с", "характеристика", "вариант 1с", "вариант", "характеристика_1с"),
    "name": ("наименование", "номенклатура", "материал"),
    "manufacturer": ("производитель",),
    "supplier": ("поставщик",),
    "material_type": ("тип материала", "тип", "вид материала", "тип сырья", "вид сырья"),
    "technological_code": (
        "технологическое обозначение",
        "тех обозначение",
        "обозначение",
        "тех. обозначение",
        "технологический код",
    ),
    "gsm": ("плотность г/м²", "плотность г/м2", "плотность", "граммаж", "грамматура", "gsm"),
    "roll_width_mm": ("ширина рулона мм", "ширина рулона", "ширина, мм", "ширина"),
    "price_rub_t": ("цена ₽/т", "цена руб/т", "цена руб./т", "цена", "цена за тонну"),
    "price_date": ("дата цены", "дата прайса", "дата актуальности цены"),
    "stock_kg": ("остаток кг", "остаток, кг", "остаток", "склад кг"),
    "stock_date": ("дата остатка", "дата склада", "дата актуальности остатка"),
    "procurement_status": ("статус", "статус закупки", "доступность"),
    "color": ("цвет", "поверхность", "цвет/поверхность"),
}

REQUIRED_FIELDS = ("code_1c", "name", "material_type", "gsm", "roll_width_mm", "price_rub_t")

STATUS_MAP = {
    "закупается": "active",
    "активен": "active",
    "активная": "active",
    "рабочая": "active",
    "рабочая цена": "active",
    "временно не закупается": "temporary_no_purchase",
    "не закупается": "temporary_no_purchase",
    "только остатки": "stock_only",
    "остатки": "stock_only",
    "недоступно": "unavailable",
    "недоступен": "unavailable",
    "требует классификации": "requires_classification",
}


@dataclass(frozen=True)
class ImportIssue:
    row_number: int
    field: str
    message: str
    value: object | None = None


@dataclass(frozen=True)
class MaterialImportRow:
    row_number: int
    code_1c: str
    variant_1c: str | None
    name: str
    manufacturer: str | None
    supplier: str | None
    material_type: str
    technological_code: str | None
    gsm: float
    roll_width_mm: float
    price_rub_t: float
    price_date: str | None
    stock_kg: float | None
    stock_date: str | None
    procurement_status: str
    color: str | None


class ImportFormatError(ValueError):
    pass


def _norm(value: object) -> str:
    s = "" if value is None else str(value)
    s = unicodedata.normalize("NFKC", s).strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref.upper())
    if not letters:
        return 0
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(path))
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    result = []
    for si in root.findall("a:si", ns):
        parts = [t.text or "" for t in si.findall(".//a:t", ns)]
        result.append("".join(parts))
    return result


def _first_sheet_path(zf: zipfile.ZipFile) -> str:
    ns_main = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_doc_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    sheet = wb.find("a:sheets/a:sheet", ns_main)
    if sheet is None:
        raise ImportFormatError("В XLSX не найдено ни одного листа")
    rel_id = sheet.attrib.get(f"{{{rel_doc_ns}}}id")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    for rel in rels.findall("r:Relationship", rel_ns):
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"]
            if target.startswith("/"):
                return target.lstrip("/")
            return str(PurePosixPath("xl") / target)
    raise ImportFormatError("Не удалось определить первый лист XLSX")


def read_first_sheet_xlsx(content: bytes) -> list[list[object | None]]:
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ImportFormatError("Файл не является корректным XLSX") from exc

    with zf:
        shared = _shared_strings(zf)
        sheet_path = _first_sheet_path(zf)
        try:
            root = ET.fromstring(zf.read(sheet_path))
        except KeyError as exc:
            raise ImportFormatError("Не удалось прочитать первый лист XLSX") from exc
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows: list[list[object | None]] = []
        for row in root.findall(".//a:sheetData/a:row", ns):
            current: list[object | None] = []
            for cell in row.findall("a:c", ns):
                idx = _column_index(cell.attrib.get("r", "A1"))
                while len(current) <= idx:
                    current.append(None)
                cell_type = cell.attrib.get("t")
                v = cell.find("a:v", ns)
                if cell_type == "inlineStr":
                    parts = [t.text or "" for t in cell.findall(".//a:t", ns)]
                    value: object | None = "".join(parts)
                elif v is None:
                    value = None
                elif cell_type == "s":
                    try:
                        value = shared[int(v.text or "0")]
                    except (ValueError, IndexError):
                        value = v.text
                elif cell_type == "b":
                    value = v.text == "1"
                elif cell_type in ("str", "e"):
                    value = v.text
                else:
                    raw = v.text or ""
                    try:
                        value = float(raw)
                        if value.is_integer():
                            value = int(value)
                    except ValueError:
                        value = raw
                current[idx] = value
            rows.append(current)
        return rows


def read_csv(content: bytes) -> list[list[object | None]]:
    text = None
    for enc in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ImportFormatError("Не удалось определить кодировку CSV")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    return [list(row) for row in csv.reader(text.splitlines(), dialect)]


def _to_float(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).replace("\u00a0", " ").strip().replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in ("-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_date(value: object | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and 1 <= float(value) <= 100000:
        try:
            return (date(1899, 12, 30) + timedelta(days=int(float(value)))).isoformat()
        except OverflowError:
            pass
    s = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def _normalize_status(value: object | None) -> str:
    if value is None or str(value).strip() == "":
        return "active"
    s = _norm(value)
    if s in STATUS_MAP:
        return STATUS_MAP[s]
    for key, mapped in STATUS_MAP.items():
        if key in s:
            return mapped
    if s in {"active", "stock_only", "temporary_no_purchase", "unavailable", "requires_classification"}:
        return s
    return "requires_classification"


def _find_header_row(rows: list[list[object | None]]) -> tuple[int, dict[int, str]]:
    alias_to_field: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            alias_to_field[_norm(alias)] = field

    best: tuple[int, dict[int, str]] | None = None
    for ridx, row in enumerate(rows[:30]):
        mapping: dict[int, str] = {}
        for cidx, value in enumerate(row):
            key = _norm(value)
            if key in alias_to_field:
                mapping[cidx] = alias_to_field[key]
        if best is None or len(mapping) > len(best[1]):
            best = (ridx, mapping)

    if best is None or len(best[1]) < 4:
        raise ImportFormatError(
            "Не найден заголовок таблицы 1С. Проверьте названия колонок или используйте утверждённый шаблон."
        )
    missing = [field for field in REQUIRED_FIELDS if field not in best[1].values()]
    if missing:
        raise ImportFormatError("Не хватает обязательных колонок: " + ", ".join(missing))
    return best


def _text(value: object | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _validate_row(raw: dict[str, object | None], row_number: int) -> tuple[MaterialImportRow | None, list[ImportIssue]]:
    issues: list[ImportIssue] = []

    def issue(field: str, message: str, value: object | None = None) -> None:
        issues.append(ImportIssue(row_number=row_number, field=field, message=message, value=value))

    code = _text(raw.get("code_1c"))
    name = _text(raw.get("name"))
    material_type = _text(raw.get("material_type"))
    gsm = _to_float(raw.get("gsm"))
    width = _to_float(raw.get("roll_width_mm"))
    price = _to_float(raw.get("price_rub_t"))
    stock = _to_float(raw.get("stock_kg"))

    if not code:
        issue("code_1c", "Не указан код номенклатуры 1С", raw.get("code_1c"))
    if not name:
        issue("name", "Не указано наименование материала", raw.get("name"))
    if not material_type:
        issue("material_type", "Не указан тип сырья; материал нельзя автоматически классифицировать", raw.get("material_type"))
    if gsm is None or gsm <= 0:
        issue("gsm", "Грамматура должна быть больше 0", raw.get("gsm"))
    if width is None or width <= 0:
        issue("roll_width_mm", "Ширина рулона должна быть больше 0", raw.get("roll_width_mm"))
    if price is None or price <= 0:
        issue("price_rub_t", "Цена должна быть больше 0", raw.get("price_rub_t"))
    if stock is not None and stock < 0:
        issue("stock_kg", "Остаток не может быть отрицательным", raw.get("stock_kg"))

    status = _normalize_status(raw.get("procurement_status"))
    if status == "requires_classification" and raw.get("procurement_status") not in (None, ""):
        issue(
            "procurement_status",
            "Статус не распознан; материал помечен как требующий классификации",
            raw.get("procurement_status"),
        )

    fatal_fields = {"code_1c", "name", "material_type", "gsm", "roll_width_mm", "price_rub_t", "stock_kg"}
    if any(x.field in fatal_fields for x in issues):
        return None, issues

    return MaterialImportRow(
        row_number=row_number,
        code_1c=code or "",
        variant_1c=_text(raw.get("variant_1c")),
        name=name or "",
        manufacturer=_text(raw.get("manufacturer")),
        supplier=_text(raw.get("supplier")),
        material_type=material_type or "",
        technological_code=_text(raw.get("technological_code")),
        gsm=float(gsm),
        roll_width_mm=float(width),
        price_rub_t=float(price),
        price_date=_to_date(raw.get("price_date")),
        stock_kg=float(stock) if stock is not None else None,
        stock_date=_to_date(raw.get("stock_date")),
        procurement_status=status,
        color=_text(raw.get("color")),
    ), issues


def parse_material_import(content: bytes, filename: str) -> dict:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        rows = read_first_sheet_xlsx(content)
    elif lower.endswith((".csv", ".txt")):
        rows = read_csv(content)
    else:
        raise ImportFormatError("Поддерживаются XLSX и CSV")

    if not rows:
        raise ImportFormatError("Файл пуст")

    header_index, mapping = _find_header_row(rows)
    parsed: list[MaterialImportRow] = []
    issues: list[ImportIssue] = []
    seen: set[tuple[str, str]] = set()
    total_data_rows = 0

    for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(value not in (None, "") for value in row):
            continue
        total_data_rows += 1
        raw = {field: row[col] if col < len(row) else None for col, field in mapping.items()}
        item, row_issues = _validate_row(raw, row_index)
        issues.extend(row_issues)
        if item is None:
            continue

        key = (item.code_1c.strip().upper(), (item.variant_1c or "").strip().upper())
        if key in seen:
            issues.append(
                ImportIssue(
                    row_number=row_index,
                    field="duplicate",
                    message="Повтор кода 1С + характеристики внутри импортируемого файла",
                    value=" / ".join(x for x in key if x),
                )
            )
            continue
        seen.add(key)
        parsed.append(item)

    rows_out = [asdict(x) for x in parsed]
    issues_out = [asdict(x) for x in issues]
    return {
        "format": "KE_BOX_CALC_1C_MATERIALS_v1",
        "file_name": filename,
        "header_row": header_index + 1,
        "rows": rows_out,
        "issues": issues_out[:500],
        "stats": {
            "rows_total": total_data_rows,
            "rows_valid": len(rows_out),
            "rows_invalid": max(0, total_data_rows - len(rows_out)),
            "issues": len(issues_out),
        },
    }
