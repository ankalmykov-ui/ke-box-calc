from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import PurePosixPath
import csv
import hashlib
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

from app.calc.grade import normalize_grade, ect_norm
from .materials_1c import ImportFormatError, _column_index, _shared_strings, _to_float, _to_date, read_csv


ALIASES = {
    "date": ("дата", "дата испытания"),
    "tech_card": ("техкарта", "№ техкарты", "номер техкарты", "тех. карта"),
    "protocol": ("протокол", "№ протокола", "номер протокола"),
    "client": ("клиент", "заказчик"),
    "product": ("изделие", "вид изделия", "наименование изделия"),
    "size": ("размер", "размер изделия", "формат"),
    "declared_grade": ("заявленная марка", "марка заявл", "марка по заказу", "марка"),
    "actual_grade": ("фактическая марка", "марка факт", "факт марка"),
    "profile": ("профиль", "гофра", "тип гофра"),
    "layer1": ("слой 1", "1 слой", "наружный слой", "верхний слой"),
    "layer2": ("слой 2", "2 слой", "гофрируемый слой", "флютинг 1"),
    "layer3": ("слой 3", "3 слой", "внутренний слой"),
    "layer4": ("слой 4", "4 слой", "флютинг 2"),
    "layer5": ("слой 5", "5 слой"),
    "ect_norm": ("ect норма", "норма ect", "сопротивление торцевому сжатию норма"),
    "ect_actual": ("ect факт", "ect", "сопротивление торцевому сжатию факт"),
    "bct_actual": ("bct факт", "bct", "сопротивление сжатию коробки"),
    "moisture": ("влажность", "влажность %"),
    "line": ("линия", "станок", "машина"),
    "customer_requirement": ("требование клиента", "требования клиента", "примечание"),
}


def _norm(v) -> str:
    s = "" if v is None else str(v)
    s = unicodedata.normalize("NFKC", s).lower().replace("ё", "е").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _workbook_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    main_ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_doc_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    targets = {r.attrib.get("Id"): r.attrib.get("Target") for r in rels.findall("r:Relationship", rel_ns)}
    out = []
    for sh in wb.findall("a:sheets/a:sheet", main_ns):
        name = sh.attrib.get("name", "Sheet")
        rid = sh.attrib.get(f"{{{rel_doc_ns}}}id")
        target = targets.get(rid)
        if not target:
            continue
        path = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
        out.append((name, path))
    return out


def read_all_sheets_xlsx(content: bytes) -> dict[str, list[list[object | None]]]:
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ImportFormatError("Файл не является корректным XLSX") from exc
    result = {}
    with zf:
        shared = _shared_strings(zf)
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for name, path in _workbook_sheets(zf):
            try:
                root = ET.fromstring(zf.read(path))
            except KeyError:
                continue
            rows = []
            for row in root.findall(".//a:sheetData/a:row", ns):
                current = []
                for cell in row.findall("a:c", ns):
                    idx = _column_index(cell.attrib.get("r", "A1"))
                    while len(current) <= idx:
                        current.append(None)
                    t = cell.attrib.get("t")
                    v = cell.find("a:v", ns)
                    if t == "inlineStr":
                        value = "".join(x.text or "" for x in cell.findall(".//a:t", ns))
                    elif v is None:
                        value = None
                    elif t == "s":
                        try: value = shared[int(v.text or "0")]
                        except Exception: value = v.text
                    else:
                        raw = v.text or ""
                        try:
                            value = float(raw)
                            if value.is_integer(): value = int(value)
                        except ValueError:
                            value = raw
                    current[idx] = value
                rows.append(current)
            result[name] = rows
    return result


def _header_map(rows: list[list[object | None]]) -> tuple[int, dict[int, str]] | None:
    alias = {}
    for field, names in ALIASES.items():
        for n in names:
            alias[_norm(n)] = field
    best = None
    for ridx, row in enumerate(rows[:35]):
        mapping = {}
        for cidx, v in enumerate(row):
            key = _norm(v)
            if key in alias:
                mapping[cidx] = alias[key]
        if best is None or len(mapping) > len(best[1]):
            best = (ridx, mapping)
    if best is None or len(best[1]) < 4:
        return None
    return best


def _profile(v) -> str | None:
    if v is None or str(v).strip() == "": return None
    s = str(v).strip().upper().replace("Е", "E").replace("В", "B").replace("С", "C")
    s = s.replace(" ", "")
    aliases = {"EB":"BE", "EC":"CE", "CB":"BC"}
    return aliases.get(s, s)


def _composition_key(values: list[str | None]) -> str | None:
    parts = [re.sub(r"\s+", " ", str(x).strip().upper()) for x in values if x not in (None, "")]
    return " | ".join(parts) if parts else None


def normalize_lab_sheet(sheet_name: str, rows: list[list[object | None]]) -> dict:
    found = _header_map(rows)
    if found is None:
        return {"sheet": sheet_name, "recognized": False, "rows": [], "issues": [], "stats": {"valid": 0}}
    hidx, cmap = found
    out, issues = [], []
    seen = set()
    for ridx, row in enumerate(rows[hidx+1:], start=hidx+2):
        if not any(x not in (None, "") for x in row):
            continue
        raw = {field: row[c] if c < len(row) else None for c, field in cmap.items()}
        if not any(raw.get(k) not in (None, "") for k in ("protocol", "tech_card", "ect_actual", "bct_actual", "declared_grade", "product")):
            continue
        layers = [raw.get(f"layer{i}") for i in range(1, 6)]
        declared = normalize_grade(str(raw.get("declared_grade"))) if raw.get("declared_grade") not in (None, "") else None
        actual = normalize_grade(str(raw.get("actual_grade"))) if raw.get("actual_grade") not in (None, "") else None
        ect = _to_float(raw.get("ect_actual"))
        norm = _to_float(raw.get("ect_norm"))
        if norm is None and declared:
            norm = ect_norm(declared)
        passed = (ect >= norm) if ect is not None and norm is not None else None
        key_src = "|".join(str(raw.get(k) or "") for k in ("date", "tech_card", "protocol", "client", "product", "ect_actual"))
        external_key = hashlib.sha1((sheet_name + "|" + key_src).encode("utf-8")).hexdigest()
        duplicate = external_key in seen
        seen.add(external_key)
        rec = {
            "source_sheet": sheet_name, "source_row": ridx, "external_test_key": external_key, "duplicate_in_file": duplicate,
            "date": _to_date(raw.get("date")), "tech_card": str(raw.get("tech_card") or "").strip() or None,
            "protocol": str(raw.get("protocol") or "").strip() or None, "client": str(raw.get("client") or "").strip() or None,
            "product": str(raw.get("product") or "").strip() or None, "size": str(raw.get("size") or "").strip() or None,
            "declared_grade": declared, "actual_grade": actual, "profile": _profile(raw.get("profile")),
            "layers": [str(x).strip() if x not in (None, "") else None for x in layers], "composition_key": _composition_key(layers),
            "ect_norm": norm, "ect_actual": ect, "bct_actual": _to_float(raw.get("bct_actual")),
            "moisture": _to_float(raw.get("moisture")), "line": str(raw.get("line") or "").strip() or None,
            "customer_requirement": str(raw.get("customer_requirement") or "").strip() or None, "passed": passed,
        }
        if duplicate:
            issues.append({"row_number": ridx, "field": "duplicate", "message": "Повтор записи внутри импортируемого файла"})
        out.append(rec)
    return {"sheet": sheet_name, "recognized": True, "header_row": hidx+1, "rows": out, "issues": issues, "stats": {"valid": len(out), "issues": len(issues)}}


def parse_lab_import(content: bytes, filename: str) -> dict:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "xlsx":
        sheets = read_all_sheets_xlsx(content)
    elif ext in {"csv", "txt"}:
        sheets = {"CSV": read_csv(content)}
    else:
        raise ImportFormatError("Поддерживаются XLSX и CSV")
    parsed = [normalize_lab_sheet(name, rows) for name, rows in sheets.items()]
    recognized = [x for x in parsed if x["recognized"]]
    rows = [r for s in recognized for r in s["rows"]]
    issues = [i for s in recognized for i in s["issues"]]
    return {
        "format": "KE_BOX_CALC_LAB_v1", "file_name": filename,
        "sheets": [{k: v for k, v in s.items() if k != "rows"} for s in parsed],
        "stats": {"sheets_total": len(parsed), "sheets_recognized": len(recognized), "rows_valid": len(rows), "issues": len(issues)},
        "rows": rows, "issues": issues[:300],
    }
