from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import re
import zipfile
import xml.etree.ElementTree as ET

from .materials_1c import ImportFormatError


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass(frozen=True)
class InventoryPreviewRow:
    row_number: int
    warehouse_name: str
    item_name: str
    material_type: str
    gsm: float | None
    roll_width_mm: float | None
    accounting_quantity_kg: float | None
    accounting_price_rub_kg: float | None
    accounting_price_rub_t: float | None
    accounting_value_rub: float | None
    status: str
    issues: list[str]


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _cell_text(cell: ET.Element) -> str:
    text = "".join(node.text or "" for node in cell.findall(".//w:t", WORD_NS))
    return re.sub(r"\s+", " ", text).strip()


def read_docx_tables(content: bytes) -> list[list[str]]:
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ImportFormatError("Файл не является корректным DOCX") from exc

    with archive:
        try:
            document = ET.fromstring(archive.read("word/document.xml"))
        except (KeyError, ET.ParseError) as exc:
            raise ImportFormatError("Не удалось прочитать таблицу DOCX") from exc

    rows: list[list[str]] = []
    for table in document.findall(".//w:tbl", WORD_NS):
        for row in table.findall("w:tr", WORD_NS):
            cells = [_cell_text(cell) for cell in row.findall("w:tc", WORD_NS)]
            if any(cells):
                rows.append(cells)
    return rows


def _gsm_and_width(name: str) -> tuple[float | None, float | None]:
    values = [float(value) for value in re.findall(r"(?<!\d)(\d{2,4})(?!\d)", name)]
    width_index = next((index for index, value in enumerate(values) if 1000 <= value <= 3000), None)
    if width_index is None:
        return None, None
    width = values[width_index]
    gsm = next((value for value in reversed(values[:width_index]) if 60 <= value <= 500), None)
    return gsm, width


def parse_inventory_import(content: bytes, filename: str) -> dict:
    if not filename.lower().endswith(".docx"):
        raise ImportFormatError("Для учётной выгрузки 1С на этом этапе поддерживается DOCX")

    source_rows = read_docx_tables(content)
    if not source_rows:
        raise ImportFormatError("В DOCX не найдено таблиц с остатками")

    current_warehouse: str | None = None
    reported_total_kg: float | None = None
    parsed: list[InventoryPreviewRow] = []

    for row_number, cells in enumerate(source_rows, start=1):
        name, quantity_raw, price_raw, value_raw = (cells + ["", "", "", ""])[:4]
        normalized_name = name.strip()

        if normalized_name.lower() in {"склад", "номенклатура"}:
            continue
        if normalized_name.lower() == "итого":
            reported_total_kg = _number(quantity_raw)
            continue

        is_material = normalized_name.startswith(("Бумага ", "Картон "))
        if not is_material:
            if normalized_name and _number(quantity_raw) is not None:
                current_warehouse = normalized_name
            continue
        if current_warehouse is None:
            raise ImportFormatError(f"Строка {row_number}: материал найден раньше заголовка склада")

        material_type = "fluting" if normalized_name.startswith("Бумага ") else "liner"
        gsm, width = _gsm_and_width(normalized_name)
        quantity = _number(quantity_raw)
        price_kg = _number(price_raw)
        value = _number(value_raw)
        issues: list[str] = []

        if quantity is None:
            issues.append("Не заполнен учётный остаток")
        elif quantity < 0:
            issues.append("Учётный остаток не может быть отрицательным")
        if gsm is None:
            issues.append("Не удалось определить грамматуру из наименования")
        if width is None:
            issues.append("Не удалось определить ширину рулона из наименования")
        if price_kg is None:
            issues.append("Не заполнена учётная цена")
        elif price_kg < 0:
            issues.append("Отрицательная учётная цена; требуется проверка")

        fatal = quantity is None or quantity < 0 or gsm is None or width is None
        status = "error" if fatal else ("warning" if issues else "ready")
        parsed.append(
            InventoryPreviewRow(
                row_number=row_number,
                warehouse_name=current_warehouse,
                item_name=normalized_name,
                material_type=material_type,
                gsm=gsm,
                roll_width_mm=width,
                accounting_quantity_kg=quantity,
                accounting_price_rub_kg=price_kg,
                accounting_price_rub_t=price_kg * 1000 if price_kg is not None and price_kg >= 0 else None,
                accounting_value_rub=value,
                status=status,
                issues=issues,
            )
        )

    if not parsed:
        raise ImportFormatError("В DOCX не найдено строк номенклатуры")

    calculated_total_kg = sum(row.accounting_quantity_kg or 0 for row in parsed)
    rows_out = [asdict(row) for row in parsed]
    return {
        "format": "KE_BOX_CALC_1C_INVENTORY_DOCX_v1",
        "file_name": filename,
        "source_role": "inventory_reference_only",
        "can_apply": False,
        "rows": rows_out,
        "stats": {
            "rows_total": len(parsed),
            "rows_ready": sum(row.status == "ready" for row in parsed),
            "rows_warning": sum(row.status == "warning" for row in parsed),
            "rows_error": sum(row.status == "error" for row in parsed),
            "missing_quantity": sum(row.accounting_quantity_kg is None for row in parsed),
            "negative_price": sum(row.accounting_price_rub_kg is not None and row.accounting_price_rub_kg < 0 for row in parsed),
            "warehouses": sorted({row.warehouse_name for row in parsed}),
            "calculated_total_kg": calculated_total_kg,
            "reported_total_kg": reported_total_kg,
            "totals_match": reported_total_kg is not None and abs(calculated_total_kg - reported_total_kg) < 0.001,
        },
    }
