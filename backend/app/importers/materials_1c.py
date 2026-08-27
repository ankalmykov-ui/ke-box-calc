from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import PurePosixPath
import csv
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "code_1c": ("–∫–æ–¥ 1—Å", "–∫–æ–¥", "–∫–æ–¥ –Ω–æ–º–µ–Ω–∫–ª–∞—Ç—É—Ä—ã", "–∫–æ–¥_1—Å"),
    "variant_1c": ("—Ö–∞—Ä–∞–∫—Ç–µ—Ä–∏—Å—Ç–∏–∫–∞ 1—Å", "—Ö–∞—Ä–∞–∫—Ç–µ—Ä–∏—Å—Ç–∏–∫–∞", "–≤–∞—Ä–∏–∞–Ω—Ç 1—Å", "–≤–∞—Ä–∏–∞–Ω—Ç", "—Ö–∞—Ä–∞–∫—Ç–µ—Ä–∏—Å—Ç–∏–∫–∞_1—Å"),
    "name": ("–Ω–∞–∏–º–µ–Ω–æ–≤–∞–Ω–∏–µ", "–Ω–æ–º–µ–Ω–∫–ª–∞—Ç—É—Ä–∞", "–º–∞—Ç–µ—Ä–∏–∞–ª"),
    "manufacturer": ("–ø—Ä–æ–∏–∑–≤–æ–¥–∏—Ç–µ–ª—å",),
    "supplier": ("–ø–æ—Å—Ç–∞–≤—â–∏–∫",),
    "material_type": ("—Ç–∏–ø –º–∞—Ç–µ—Ä–∏–∞–ª–∞", "—Ç–∏–ø", "–≤–∏–¥ –º–∞—Ç–µ—Ä–∏–∞–ª–∞"),
    "technological_code": ("—Ç–µ—Ö–Ω–æ–ª–æ–≥–∏—á–µ—Å–∫–æ–µ –æ–±–æ–∑–Ω–∞—á–µ–Ω–∏–µ", "—Ç–µ—Ö –æ–±–æ–∑–Ω–∞—á–µ–Ω–∏–µ", "–æ–±–æ–∑–Ω–∞—á–µ–Ω–∏–µ", "—Ç–µ—Ö. –æ–±–æ–∑–Ω–∞—á–µ–Ω–∏–µ"),
    "gsm": ("–ø–ª–æ—Ç–Ω–æ—Å—Ç—å –≥/–º¬≤", "–ø–ª–æ—Ç–Ω–æ—Å—Ç—å –≥/–º2", "–ø–ª–æ—Ç–Ω–æ—Å—Ç—å", "–≥—Ä–∞–º–º–∞–∂", "gsm"),
    "roll_width_mm": ("—à–∏—Ä–∏–Ω–∞ —Ä—É–ª–æ–Ω–∞ –º–º", "—à–∏—Ä–∏–Ω–∞ —Ä—É–ª–æ–Ω–∞", "—à–∏—Ä–∏–Ω–∞, –º–º", "—à–∏—Ä–∏–Ω–∞"),
    "price_rub_t": ("—Ü–µ–Ω–∞ ‚ÇΩ/—Ç", "—Ü–µ–Ω–∞ —Ä—É–±/—Ç", "—Ü–µ–Ω–∞ —Ä—É–±./—Ç", "—Ü–µ–Ω–∞", "—Ü–µ–Ω–∞ –∑–∞ —Ç–æ–Ω–Ω—É"),
    "price_date": ("–¥–∞—Ç–∞ —Ü–µ–Ω—ã", "–¥–∞—Ç–∞ –ø—Ä–∞–π—Å–∞", "–¥–∞—Ç–∞ –∞–∫—Ç—É–∞–ª—å–Ω–æ—Å—Ç–∏ —Ü–µ–Ω—ã"),
    "stock_kg": ("–æ—Å—Ç–∞—Ç–æ–∫ –∫–≥", "–æ—Å—Ç–∞—Ç–æ–∫, –∫–≥", "–æ—Å—Ç–∞—Ç–æ–∫", "—Å–∫–ª–∞–¥ –∫–≥"),
    "stock_date": ("–¥–∞—Ç–∞ –æ—Å—Ç–∞—Ç–∫–∞", "–¥–∞—Ç–∞ —Å–∫–ª–∞–¥–∞", "–¥–∞—Ç–∞ –∞–∫—Ç—É–∞–ª—å–Ω–æ—Å—Ç–∏ –æ—Å—Ç–∞—Ç–∫–∞"),
    "procurement_status": ("—Å—Ç–∞—Ç—É—Å", "—Å—Ç–∞—Ç—É—Å –∑–∞–∫—É–ø–∫–∏", "–¥–æ—Å—Ç—É–ø–Ω–æ—Å—Ç—å"),
    "color": ("—Ü–≤–µ—Ç", "–ø–æ–≤–µ—Ä—Ö–Ω–æ—Å—Ç—å", "—Ü–≤–µ—Ç/–ø–æ–≤–µ—Ä—Ö–Ω–æ—Å—Ç—å"),
}

REQUIRED_FIELDS = ("code_1c", "name", "material_type", "gsm", "roll_width_mm", "price_rub_t")

STATUS_MAP = {
    "–∑–∞–∫—É–ø–∞–µ—Ç—Å—è": "active",
    "–∞–∫—Ç–∏–≤–µ–Ω": "active",
    "–∞–∫—Ç–∏–≤–Ω–∞—è": "active",
    "—Ä–∞–±–æ—á–∞—è": "active",
    "—Ä–∞–±–æ—á–∞—è —Ü–µ–Ω–∞": "active",
    "–≤—Ä–µ–º–µ–Ω–Ω–æ –Ω–µ –∑–∞–∫—É–ø–∞–µ—Ç—Å—è": "temporary_no_purchase",
    "–Ω–µ –∑–∞–∫—É–ø–∞–µ—Ç—Å—è": "temporary_no_purchase",
    "—Ç–æ–ª—å–∫–æ –æ—Å—Ç–∞—Ç–∫–∏": "stock_only",
    "–æ—Å—Ç–∞—Ç–∫–∏": "stock_only",
    "–Ω–µ–¥–æ—Å—Ç—É–ø–Ω–æ": "unavailable",
    "–Ω–µ–¥–æ—Å—Ç—É–ø–µ–Ω": "unavailable",
    "—Ç—Ä–µ–±—É–µ—Ç –∫–ª–∞—Å—Å–∏—Ñ–∏–∫–∞—Ü–∏–∏": "requires_classification",
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
    s = unicodedata.normalize("NFKC", s).strip().lower().replace("—ë", "–µ")
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
    ns_rel = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    sheet = wb.find("a:sheets/a:sheet", ns_main)
    if sheet is None:
        raise ImportFormatError("–í XLSX –Ω–µ –Ω–∞–π–¥–µ–Ω–æ –Ω–∏ –æ–¥–Ω–æ–≥–æ –ª–∏—Å—Ç–∞")
    rel_id = sheet.attrib.get(f"{{{ns_rel['r']}}}id")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    for rel in rels.findall("r:Relationship", rel_ns):
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"]
            if target.startswith("/"):
                return target.lstrip("/")
            return str(PurePosixPath("xl") / target)
    raise ImportFormatError("–ù–µ —É–¥–∞–ª–æ—Å—å –æ–ø—Ä–µ–¥–µ–ª–∏—Ç—å –ø–µ—Ä–≤—ã–π –ª–∏—Å—Ç XLSX")


def read_first_sheet_xlsx(content: bytes) -> list[list[object | None]]:
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ImportFormatError("–§–∞–π–ª –Ω–µ —è–≤–ª—è–µ—Ç—Å—è –∫–æ—Ä—Ä–µ–∫—Ç–Ω—ã–º XLSX") from exc
    with zf:
        shared = _shared_strings(zf)
        sheet_path = _first_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))
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
                    value = (v.text == "1")
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
        raise ImportFormatError("–ù–µ —É–¥–∞–ª–æ—Å—å –æ–ø—Ä–µ–¥–µ–ª–∏—Ç—å –∫–æ–¥–∏—Ä–æ–≤–∫—É CSV")
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
        # Excel 1900 date system. 1899-12-30 handles Excel's leap-year quirk.
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
    return "requires_classification"


def _find_header_row(rows: list[list[object | None]]) -> tuple[int, dict[int, str]]:
    alias_to_field: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            alias_to_field[_norm(alias)] = field

    best: tuple[int, dict[int, str] | None = None
    for ridx, row in enumerate(rows[:30]):
        mapping: dict[int, str] = {}
        for cidx, value in enumerate(row):
            key = _norm(value)
            if key in alias_to_field:
                mapping[cidx] = alias_to_field[key]
        if best is None or len(mapping) > len(best[1]):
            best = (ridx, mapping)
    if best is None or len(best[1]) < 4:
        raise ImportFormatError("–ù–µ –Ω–∞–π–¥–µ–Ω –∑–∞–≥–æ–ª–æ–≤–æ–∫ —Ç–∞–±–ª–∏—Ü—ã 1–°. –ü—Ä–æ–≤–µ—Ä—å—Ç–µ –Ω–∞–∑–≤–∞–Ω–∏—è —Ä–æ–ª–æ–Ω–æ–∫.")
    missing = [f for f in REQUIRED_FIELDS if f not in best[1].values()]
    if missing:
        raise ImportFormatError("–ù–µ —Ö–≤–∞—Ç–∞–µ—Ç –æ–±—è–∑–∞—Ç–µ–ª—å–Ω—ã—Ö –∫–æ–ª–æ–Ω–æ–∫""≤"¬"Ê¶ˆñ‚Ü÷ó76ñÊríê¢&WGW&‚&W7@††¶FVbÊ˜&÷∆ó¶Uˆ÷FW&ñ≈˜&˜w2á&˜w3¢∆ó7E∂∆ó7E∂ˆ&¶V7B¬ÊˆÊU’“¬÷Ö˜&˜w3¢ñÁB“Sí”‚Fñ7C†¢ñbÊ˜B&˜w3†¢&ó6Rñ◊˜'Df˜&÷DW'&˜"Ç-
Mù≤˝=""ê¢ÜVFW%ˆñGÇ¬6ˆ∆÷“ˆfñÊEˆÜVFW%˜&˜rá&˜w2ê¢Ê˜&÷∆ó¶VC¢∆ó7E¥÷FW&ñƒñ◊˜'E&˜u““µ–¢ó77VW3¢∆ó7E¥ñ◊˜'Dó77VU““µ–†¢f˜"WÜ6V≈ˆñGÇ¬&˜rñ‚VÁV÷W&FRá&˜w5∂ÜVFW%ˆñGÇ≤¢ÜVFW%ˆñGÇ≤≤÷Ö˜&˜w5“¬7F'C÷ÜVFW%ˆñGÇ≤"ì†¢ñbÊ˜BÁíábÊ˜Bñ‚ÑÊˆÊR¬""íf˜"bñ‚&˜rì†¢6ˆÁFñÁVP¢&s¢Fñ7E∑7G"¬ˆ&¶V7B¬ÊˆÊU““∑–¢f˜"6ñGÇ¬fñV∆Bñ‚6ˆ∆÷ÊóFV◊2Çì†¢&u∂fñV∆E““&˜u∂6ñGÖ“ñb6ñGÇ¬∆V‚á&˜ríV«6RÊˆÊP†¢6ˆFR“""ñb&rÊvWBÇ&6ˆFUÛ2"íó2ÊˆÊRV«6R7G"á&rÊvWBÇ&6ˆFUÛ2"ííÁ7G&óÇê¢Ê÷R“""ñb&rÊvWBÇ&Ê÷R"íó2ÊˆÊRV«6R7G"á&rÊvWBÇ&Ê÷R"ííÁ7G&óÇê¢◊GóR“""ñb&rÊvWBÇ&÷FW&ñ≈˜GóR"íó2ÊˆÊRV«6R7G"á&rÊvWBÇ&÷FW&ñ≈˜GóR"ííÁ7G&óÇê¢w6““˜Fıˆf∆ˆBá&rÊvWBÇ&w6“"íê¢vñGFÇ“˜Fıˆf∆ˆBá&rÊvWBÇ'&ˆ∆≈˜vñGFÖˆ÷“"íê¢&ñ6R“˜Fıˆf∆ˆBá&rÊvWBÇ'&ñ6U˜'V%˜B"íê¢7Fˆ6≤“˜Fıˆf∆ˆBá&rÊvWBÇ'7Fˆ6µˆ∂r"íê†¢&˜uˆW'&˜'2“f«6P¢f˜"fñV∆B¬f¬ñ‚ÇÇ&6ˆFUÛ2"¬6ˆFRí¬Ç&Ê÷R"¬Ê÷Rí¬Ç&÷FW&ñ≈˜GóR"¬◊GóRíì†¢ñbÊ˜Bf√†¢ó77VW2ÊVÊBÑñ◊˜'Dó77VRÜWÜ6V≈ˆñGÇ¬fñV∆B¬-Ì˝}-]ΩÕ›ÌR˝ÌΩR˝=-‚"¬&rÊvWBÜfñV∆Bííê¢&˜uˆW'&˜'2“G'VP¢f˜"fñV∆B¬f¬ñ‚ÇÇ&w6“"¬w6“í¬Ç'&ˆ∆≈˜vñGFÖˆ÷“"¬vñGFÇí¬Ç'&ñ6U˜'V%˜B"¬&ñ6Ríì†¢ñbf¬ó2ÊˆÊR˜"f¬√“†¢ó77VW2ÊVÊBÑñ◊˜'Dó77VRÜWÜ6V≈ˆñGÇ¬fñV∆B¬-ÌmçM]-Ú}çΩ‚ÌΩÕçR›=ΩÚ"¬&rÊvWBÜfñV∆Bííê¢&˜uˆW'&˜'2“G'VP¢ñb7Fˆ6≤ó2Ê˜BÊˆÊRÊB7Fˆ6≤¬†¢ó77VW2ÊVÊBÑñ◊˜'Dó77VRÜWÜ6V≈ˆñGÇ¬'7Fˆ6µˆ∂r"¬-Ì--Ì¢›RÕÌm]"Ω-¬Ì-çm-]ΩÕ›Ω¬"¬&rÊvWBÇ'7Fˆ6µˆ∂r"ííê¢&˜uˆW'&˜'2“G'VP¢ñb&˜uˆW'&˜'3†¢6ˆÁFñÁVP†¢Ê˜&÷∆ó¶VBÊVÊBÄ¢÷FW&ñƒñ◊˜'E&˜rÄ¢&˜uˆÁV÷&W#÷WÜ6V≈ˆñGÇ¿¢6ˆFUÛ3÷6ˆFR¿¢f&ñÁEÛ3“á7G"á&rÊvWBÇ'f&ñÁEÛ2"ííÁ7G&óÇíñb&rÊvWBÇ'f&ñÁEÛ2"íÊ˜Bñ‚ÑÊˆÊR¬""íV«6RÊˆÊRí¿¢Ê÷S÷Ê÷R¿¢÷ÁVf7GW&W#“á7G"á&rÊvWBÇ&÷ÁVf7GW&W""ííÁ7G&óÇíñb&rÊvWBÇ&÷ÁVf7GW&W""íÊ˜Bñ‚ÑÊˆÊR¬""íV«6RÊˆÊRí¿¢7W∆ñW#“á7G"á&rÊvWBÇ'7W∆ñW""ííÁ7G&óÇíñb&rÊvWBÇ'7W∆ñW""íÊ˜Bñ‚ÑÊˆÊR¬""íV«6RÊˆÊRí¿¢÷FW&ñ≈˜GóS÷◊GóR¿¢FV6ÜÊˆ∆ˆvñ6≈ˆ6ˆFS“á7G"á&rÊvWBÇ'FV6ÜÊˆ∆ˆvñ6≈ˆ6ˆFR"ííÁ7G&óÇíñb&rÊvWBÇ'FV6ÜÊˆ∆ˆvñ6≈ˆ6ˆFR"íÊ˜Bñ‚ÑÊˆÊR¬""íV«6RÊˆÊRí¿¢w6”÷f∆ˆBÜw6“í¿¢&ˆ∆≈˜vñGFÖˆ÷”÷f∆ˆBávñGFÇí¿¢&ñ6U˜'V%˜C÷f∆ˆBá&ñ6Rí¿¢&ñ6UˆFFS’˜FıˆFFRá&rÊvWBÇ'&ñ6UˆFFR"íí¿¢7Fˆ6µˆ∂s“Üf∆ˆBá7Fˆ6≤íñb7Fˆ6≤ó2Ê˜BÊˆÊRV«6RÊˆÊRí¿¢7Fˆ6µˆFFS’˜FıˆFFRá&rÊvWBÇ'7Fˆ6µˆFFR"íí¿¢&ˆ7W&V÷VÁE˜7FGW3’ˆÊ˜&÷∆ó¶U˜7FGW2á&rÊvWBÇ'&ˆ7W&V÷VÁE˜7FGW2"íí¿¢6ˆ∆˜#“á7G"á&rÊvWBÇ&6ˆ∆˜""ííÁ7G&óÇíñb&rÊvWBÇ&6ˆ∆˜""íÊ˜Bñ‚ÑÊˆÊR¬""íV«6RÊˆÊRí¿¢ê¢ê†¢∂Wó2“≤á"Ê6ˆFUÛ2¬"Áf&ñÁEÛ2˜"""íf˜""ñ‚Ê˜&÷∆ó¶VE–¢GW∆ñ6FW2“∆V‚Ü∂Wó2í“∆V‚á6WBÜ∂Wó2íê¢ñbGW∆ñ6FW3†¢ó77VW2ÊVÊBÑñ◊˜'Dó77VRÉ¬&∂Wí"¬b-"MùΩR›ùM]›‚˝Ì--ÌÌ"≠ΩÌ}	≠ÌB
≤
]≠-]ç-ç≠¢∂GW∆ñ6FW7“"íê†¢&WGW&‚∞¢&f˜&÷B#¢$¥UÙ$ıÖÙ4ƒ5Û5Ù‘DU$î≈5˜c"¿¢&ÜVFW%˜&˜r#¢ÜVFW%ˆñGÇ≤¿¢&6ˆ«V÷Âˆ÷ñÊr#¢∑7G"Ü6ñGÇ≤ì¢fñV∆Bf˜"6ñGÇ¬fñV∆Bñ‚6ˆ∆÷ÊóFV◊2Çó“¿¢'7FG2#¢∞¢'&˜w5˜&VB#¢÷ÇÉ¬÷ñ‚Ü∆V‚á&˜w2í“ÜVFW%ˆñGÇ“¬÷Ö˜&˜w2íí¿¢'&˜w5˜f∆ñB#¢∆V‚ÜÊ˜&÷∆ó¶VBí¿¢&ó77VW2#¢∆V‚Üó77VW2í¿¢&GW∆ñ6FUˆ∂Wó2#¢GW∆ñ6FW2¿¢“¿¢'&˜w2#¢∂6Fñ7Bá"íf˜""ñ‚Ê˜&÷∆ó¶VE“¿¢&ó77VW2#¢∂6Fñ7BÜííf˜"íñ‚ó77VW5≥£#’“¿¢–††¶FVb'6Uˆ÷FW&ñ≈ˆñ◊˜'BÜ6ˆÁFVÁC¢'óFW2¬fñ∆VÊ÷S¢7G"í”‚Fñ7C†¢WáB“fñ∆VÊ÷RÊ∆˜vW"ÇíÁ'7∆óBÇ"‚"¬ï≤”“ñb"‚"ñ‚fñ∆VÊ÷RV«6R" ¢ñbWáB”“'Ü«7Ç#†¢&˜w2“&VEˆfó'7E˜6ÜVWE˜Ü«7ÇÜ6ˆÁFVÁBê¢V∆ñbWáBñ‚Ç&77b"¬'GáB"ì†¢&˜w2“&VEˆ77bÜ6ˆÁFVÁBê¢V«6S†¢&ó6Rñ◊˜'Df˜&÷DW'&˜"Ç-	˝ÌMM]mç-Ì-ÚÑ≈5ÇÇ55b"ê¢&WGW&‚Ê˜&÷∆ó¶Uˆ÷FW&ñ≈˜&˜w2á&˜w2ê