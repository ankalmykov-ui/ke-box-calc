from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def load_equipment_reference() -> dict:
    return json.loads((DATA / "equipment_v0.6.json").read_text(encoding="utf-8"))


def _fits_rect(a: float, b: float, spec: dict, skip_feed: bool = False) -> bool:
    max_a = spec.get("skip_max_a_mm") if skip_feed and spec.get("skip_max_a_mm") else spec.get("max_a_mm")
    max_b = spec.get("skip_max_b_mm") if skip_feed and spec.get("skip_max_b_mm") else spec.get("max_b_mm")
    min_a, min_b = spec.get("min_a_mm"), spec.get("min_b_mm")
    def ok(x, y):
        return (min_a is None or x >= min_a) and (min_b is None or y >= min_b) and (max_a is None or x <= max_a) and (max_b is None or y <= max_b)
    return ok(a, b) or ok(b, a)


def _speed_estimate(machine: dict, blank_length_mm: float, blank_width_mm: float, colors: int, die_cut: bool, profile: str) -> tuple[float | None, str]:
    speed = machine.get("speed") or {}
    cruise = speed.get("cruise_per_hour")
    if not cruise:
        return None, "Скорость не откалибрована"
    sheet = machine.get("sheet") or {}
    max_a = float(sheet.get("max_a_mm") or blank_length_mm)
    max_b = float(sheet.get("max_b_mm") or blank_width_mm)
    utilization = max(blank_length_mm / max_a, blank_width_mm / max_b)
    factor = 1.0
    if utilization > 0.9:
        factor *= 0.82
    elif utilization > 0.75:
        factor *= 0.9
    elif utilization < 0.35:
        factor *= 0.88
    if colors > 1:
        factor *= max(0.82, 1 - 0.035 * (colors - 1))
    if die_cut:
        factor *= 0.92
    if profile in {"BE", "CE", "BC"}:
        factor *= 0.88
    result = float(cruise) * factor
    mechanical = speed.get("mechanical_max_per_hour")
    if mechanical:
        result = min(result, float(mechanical))
    return round(result, 0), "Расчётная скорость по редактируемой эвристической модели v0.6; требует накопления факта"


def evaluate_machine(
    machine: dict,
    blank_length_mm: float,
    blank_width_mm: float,
    profile: str,
    caliper_mm: float | None,
    panels: dict | None = None,
    colors: int = 1,
    die_cut: bool = False,
    quantity: int = 1,
    hourly_cost_rub: float | None = None,
) -> dict:
    reasons = []
    warnings = []
    profile = profile.upper()
    if profile not in set(machine.get("profiles") or []):
        reasons.append(f"Профиль {profile} не разрешён справочником")
    if colors > int(machine.get("colors") or 0):
        reasons.append(f"Требуется {colors} цветов, машина поддерживает {machine.get('colors')}")
    if not _fits_rect(blank_length_mm, blank_width_mm, machine.get("sheet") or {}, skip_feed=False):
        if _fits_rect(blank_length_mm, blank_width_mm, machine.get("sheet") or {}, skip_feed=True):
            warnings.append("Формат проходит только в режиме skip-feed")
        else:
            reasons.append("Формат заготовки вне рабочего диапазона")
    thick = machine.get("board_thickness_mm") or {}
    if caliper_mm is not None:
        if thick.get("min") is not None and caliper_mm < float(thick["min"]):
            reasons.append("Толщина меньше паспортного диапазона")
        if thick.get("max") is not None and caliper_mm > float(thick["max"]):
            reasons.append("Толщина больше паспортного диапазона")
    if panels and machine.get("flaps"):
        f = machine["flaps"]
        flap_values = [panels.get("top_flap_mm"), panels.get("bottom_flap_mm")]
        flap_values = [float(x) for x in flap_values if x is not None]
        if flap_values:
            small, large = min(flap_values), max(flap_values)
            if f.get("small_min") is not None and small < float(f["small_min"]):
                reasons.append(f"Малый клапан {small:g} мм меньше допустимого {f['small_min']} мм")
            if f.get("small_max") is not None and small > float(f["small_max"]):
                reasons.append("Малый клапан больше допустимого")
            if f.get("large_min") is not None and large < float(f["large_min"]):
                reasons.append("Большой клапан меньше допустимого")
            if f.get("large_max") is not None and large > float(f["large_max"]):
                reasons.append("Большой клапан больше допустимого")
        joint = panels.get("manufacturer_joint_mm")
        if joint is not None and f.get("glue_flap_max_width") is not None and float(joint) > float(f["glue_flap_max_width"]):
            # Warning rather than rejection: passport wording may refer to glue geometry differently.
            warnings.append("Размер стыка больше паспортной величины клеевого клапана; требуется проверка трактовки параметра")
    if machine.get("status") == "requires_passport_verification":
        warnings.append("Часть параметров машины взята из старого рабочего справочника и требует паспорта")

    feasible = not reasons
    speed, speed_note = _speed_estimate(machine, blank_length_mm, blank_width_mm, colors, die_cut, profile) if feasible else (None, "Не рассчитывается для непригодной машины")
    setup_min = float(machine.get("setup_minutes") or 0)
    production_min = (quantity / speed * 60) if speed else None
    total_min = (setup_min + production_min) if production_min is not None else None
    conversion_cost = (total_min / 60 * hourly_cost_rub) if total_min is not None and hourly_cost_rub is not None else None
    return {
        "code": machine["code"], "name": machine["name"], "model": machine.get("model"),
        "feasible": feasible, "reasons": reasons, "warnings": warnings,
        "estimated_speed_per_hour": speed, "speed_note": speed_note,
        "setup_minutes": setup_min, "production_minutes": round(production_min, 2) if production_min is not None else None,
        "total_minutes": round(total_min, 2) if total_min is not None else None,
        "conversion_cost_rub": round(conversion_cost, 2) if conversion_cost is not None else None,
        "data_status": machine.get("status"), "source": machine.get("source"),
    }


def select_machine(**kwargs) -> dict:
    data = load_equipment_reference()
    evaluations = [evaluate_machine(m, **kwargs) for m in data["machines"]]
    feasible = [x for x in evaluations if x["feasible"]]
    def key(x):
        cost = x["conversion_cost_rub"]
        total = x["total_minutes"]
        # Economic cost when known, then total time; uncalibrated speed sorts after calibrated.
        return (cost is None, cost if cost is not None else math.inf, total is None, total if total is not None else math.inf)
    feasible.sort(key=key)
    for idx, item in enumerate(feasible, start=1):
        item["rank"] = idx
    return {
        "recommended": feasible[0] if feasible else None,
        "alternatives": feasible[1:],
        "all_machines": evaluations,
        "excluded": [x for x in evaluations if not x["feasible"]],
    }
