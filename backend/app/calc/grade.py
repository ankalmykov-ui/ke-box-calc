from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def load_grade_norms() -> dict:
    return json.loads((DATA / "board_grade_norms_v0.6.json").read_text(encoding="utf-8"))


def normalize_grade(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().upper().replace(" ", "")
    if not raw:
        return None
    data = load_grade_norms()
    aliases = {k.upper().replace(" ", ""): v for k, v in data.get("aliases", {}).items()}
    if raw in aliases:
        return aliases[raw]
    raw = raw.replace("Т", "T").replace("П", "P")
    raw = re.sub(r"^(T|P)-", r"\1", raw)
    # Generic grade aliases in historical files, e.g. T23 -> lowest subclass when a precise norm is absent.
    if raw in data["grades"]:
        return raw
    if re.fullmatch(r"T2[3-7]", raw):
        candidate = raw + ".1"
        if candidate in data["grades"]:
            return candidate
    if raw == "P32":
        return "P32/1"
    return raw


def ect_norm(grade: str | None) -> float | None:
    code = normalize_grade(grade)
    if code is None:
        return None
    rec = load_grade_norms()["grades"].get(code)
    return float(rec["ect_min"]) if rec and rec.get("ect_min") is not None else None


def grade_strength_key(grade: str | None) -> tuple[float, str]:
    code = normalize_grade(grade) or ""
    norm = ect_norm(code)
    return (norm if norm is not None else -1.0, code)


def strongest_grade(grades: list[str]) -> str | None:
    values = [normalize_grade(g) for g in grades if normalize_grade(g)]
    if not values:
        return None
    return max(values, key=grade_strength_key)


def grade_meets(required_grade: str | None, actual_grade: str | None = None, ect_value: float | None = None) -> bool | None:
    required = ect_norm(required_grade)
    if required is None:
        return None
    if ect_value is not None:
        return float(ect_value) >= required
    actual = ect_norm(actual_grade)
    if actual is None:
        return None
    return actual >= required
