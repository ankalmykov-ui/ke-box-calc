from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def normalize_text(value: object) -> str:
    text = str(value or "").strip().upper()
    text = text.replace("Ё", "Е")
    return re.sub(r"\s+", " ", text)


def parse_dimensions(value: object) -> tuple[int, ...] | None:
    dimensions = tuple(int(number) for number in re.findall(r"\d+", str(value or "")))
    return dimensions if len(dimensions) in (2, 3) else None


def parse_measurements(value: object) -> tuple[Decimal, ...]:
    if value is None or isinstance(value, bool):
        return ()
    if isinstance(value, int | float | Decimal):
        return (Decimal(str(value)),)
    parsed = []
    for raw in _NUMBER.findall(str(value)):
        try:
            parsed.append(Decimal(raw.replace(",", ".")))
        except InvalidOperation:
            continue
    return tuple(parsed)


def parse_bct_kn(value: object) -> Decimal | None:
    """Normalize the laboratory column `ВСТ Факт сред.` from newtons to kN."""
    measurements_n = parse_measurements(value)
    if not measurements_n:
        return None
    average_n = sum(measurements_n) / Decimal(len(measurements_n))
    return (average_n / Decimal(1000)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def parse_required_bct_kn(value: object) -> Decimal | None:
    text = normalize_text(value)
    measurements = parse_measurements(value)
    if not measurements:
        return None
    numeric = measurements[0]
    if "КН" in text:
        return numeric.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if "Н" in text or numeric >= 100:
        return (numeric / Decimal(1000)).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
    return numeric.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def normalize_grade(value: object) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    text = text.replace("Т", "T").replace("П", "P")
    text = text.replace("В", "B").replace("С", "C").replace("Е", "E")
    return re.sub(r"[\s_-]+", "", text)


def infer_profile_from_requested_grade(value: object) -> str | None:
    grade = normalize_grade(value)
    if not grade:
        return None
    for profile in ("BC", "CE", "BE", "C", "B", "E"):
        if grade.endswith(profile):
            return profile
    return None


def normalize_material_name(value: object) -> str | None:
    """Build a strength identity independent of roll width and punctuation."""
    text = normalize_text(value)
    if not text:
        return None
    text = re.sub(r"(?<!\d)(?:1[5-9]\d{2}|2\d{3}|3000)(?!\d)", " ", text)
    text = re.sub(r"[^0-9A-ZА-Я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_layer(value: object, role: str, layer_index: int) -> dict | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    numbers = parse_measurements(raw)
    grammage = next((number for number in numbers if Decimal(60) <= number <= Decimal(400)), None)
    width = next((number for number in numbers if Decimal(1500) <= number <= Decimal(3000)), None)
    return {
        "layer_index": layer_index,
        "layer_role": role,
        "raw_material_name": raw,
        "normalized_material_name": normalize_material_name(raw),
        "grammage_g_m2": grammage,
        "source_width_mm": int(width) if width is not None else None,
    }
