from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations, product
from math import ceil, floor


@dataclass(frozen=True)
class OrderItem:
    code: str
    blank_length_mm: int
    blank_width_mm: int
    quantity: int
    profile: str
    board_grade: str


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def evaluate_layout(
    items: list[OrderItem], counts: tuple[int, ...], roll_width_mm: int, settings: dict
) -> dict | None:
    if len(items) != len(counts):
        return None
    lengths = sorted({item.blank_length_mm for item in items})
    if len(lengths) > settings["crosscut_levels"]:
        return None
    used_width = sum(
        item.blank_width_mm * count for item, count in zip(items, counts, strict=False)
    )
    if used_width > roll_width_mm or used_width > settings["working_width_mm"]:
        return None
    if sum(counts) > settings["max_streams"]:
        return None

    required_run_m = [
        Decimal(ceil(item.quantity / count) * item.blank_length_mm) / Decimal(1000)
        for item, count in zip(items, counts, strict=False)
    ]
    run_m = max(required_run_m)
    details = []
    overproduction_area = Decimal(0)
    useful_area = Decimal(0)
    for item, count in zip(items, counts, strict=False):
        cuts = floor(run_m * 1000 / item.blank_length_mm)
        produced = cuts * count
        over = max(0, produced - item.quantity)
        area = Decimal(item.blank_length_mm * item.blank_width_mm) / Decimal(1_000_000)
        ordered_area = area * item.quantity
        produced_area = area * produced
        item_overproduction_area = area * over
        useful_area += ordered_area
        overproduction_area += item_overproduction_area
        details.append(
            {
                "code": item.code,
                "cut_length_mm": item.blank_length_mm,
                "stream_width_mm": item.blank_width_mm,
                "streams": count,
                "ordered_quantity": item.quantity,
                "produced_quantity": produced,
                "overproduction_quantity": over,
                "blank_area_m2": area.quantize(Decimal("0.000001")),
                "ordered_area_m2": ordered_area.quantize(Decimal("0.001")),
                "produced_area_m2": produced_area.quantize(Decimal("0.001")),
                "overproduction_area_m2": item_overproduction_area.quantize(
                    Decimal("0.001")
                ),
            }
        )
    trim_mm = roll_width_mm - used_width
    web_area = Decimal(roll_width_mm) / Decimal(1000) * run_m
    trim_area = Decimal(trim_mm) / Decimal(1000) * run_m
    total_waste = trim_area + overproduction_area
    return {
        "roll_width_mm": roll_width_mm,
        "used_width_mm": used_width,
        "edge_trim_mm": trim_mm,
        "edge_trim_percent": (Decimal(trim_mm) / Decimal(roll_width_mm) * 100).quantize(
            Decimal("0.01")
        ),
        "run_length_m": run_m.quantize(Decimal("0.001")),
        "web_area_m2": web_area.quantize(Decimal("0.001")),
        "useful_area_m2": useful_area.quantize(Decimal("0.001")),
        "trim_area_m2": trim_area.quantize(Decimal("0.001")),
        "overproduction_area_m2": overproduction_area.quantize(Decimal("0.001")),
        "total_waste_m2": total_waste.quantize(Decimal("0.001")),
        "total_waste_percent": (total_waste / web_area * Decimal(100)).quantize(
            Decimal("0.01")
        ),
        "crosscut_lengths_mm": lengths,
        "crosscut_levels_used": len(lengths),
        "streams_total": sum(counts),
        "items": details,
    }


def ranked_layouts(items: list[OrderItem], roll_widths: list[int], settings: dict) -> list[dict]:
    variants = []
    for roll_width in sorted(set(roll_widths)):
        for counts in product(range(1, settings["max_streams"] + 1), repeat=len(items)):
            if sum(counts) > settings["max_streams"]:
                continue
            candidate = evaluate_layout(items, counts, roll_width, settings)
            if candidate:
                variants.append(candidate)
    variants.sort(
        key=lambda row: (row["total_waste_m2"], row["run_length_m"], row["roll_width_mm"])
    )
    return variants


def plan_launches(items: list[OrderItem], roll_widths: list[int], settings: dict) -> dict:
    remaining = list(items)
    launches = []
    unplanned = []
    while remaining:
        best = None
        for size in range(1, min(len(remaining), settings["max_streams"]) + 1):
            for indexes in combinations(range(len(remaining)), size):
                subset = [remaining[index] for index in indexes]
                if len({item.profile for item in subset}) != 1:
                    continue
                if len({item.blank_length_mm for item in subset}) > settings["crosscut_levels"]:
                    continue
                layouts = ranked_layouts(subset, roll_widths, settings)
                if not layouts:
                    continue
                key = (-len(subset), layouts[0]["total_waste_m2"], layouts[0]["run_length_m"])
                if best is None or key < best[0]:
                    best = (key, indexes, layouts[:15])
        if best is None:
            item = remaining.pop(0)
            unplanned.append(
                {"code": item.code, "reason": "Нет допустимого раскроя на складских ширинах"}
            )
            continue
        _, indexes, layouts = best
        selected = [remaining[index] for index in indexes]
        launches.append({"profile": selected[0].profile, "layouts": layouts})
        selected_indexes = set(indexes)
        remaining = [item for index, item in enumerate(remaining) if index not in selected_indexes]
    return {"launches": launches, "unplanned": unplanned}


def choose_composition(layout: dict, materials: list[dict], flute_factor: Decimal) -> dict | None:
    width = layout["roll_width_mm"]
    available = [
        row for row in materials if row["width_mm"] == width and Decimal(row["balance_kg"]) > 0
    ]
    liners = [row for row in available if row["material_type"] == "liner"]
    mediums = [row for row in available if row["material_type"] == "paper"]
    if not liners or not mediums:
        return None
    area = Decimal(layout["web_area_m2"])
    candidates = []
    for outer, medium, inner in product(liners, mediums, liners):
        layers = []
        required_by_material: dict[object, Decimal] = {}
        price_missing = False
        price_requires_verification = False
        total = Decimal(0)
        for role, row, coefficient in (
            ("outer", outer, Decimal(1)),
            ("fluting", medium, flute_factor),
            ("inner", inner, Decimal(1)),
        ):
            required = (
                area * Decimal(row["grammage_g_m2"]) * coefficient / Decimal(1000)
            ).quantize(Decimal("0.001"))
            required_by_material[row["id"]] = (
                required_by_material.get(row["id"], Decimal(0)) + required
            )
            price = row["price_rub_kg"]
            cost = None if price is None else _money(required * Decimal(price))
            if cost is None:
                price_missing = True
            else:
                total += cost
            if row.get("price_quality_status") == "requires_verification":
                price_requires_verification = True
            layers.append(
                {
                    "role": role,
                    "material_id": row["id"],
                    "name": row["name"],
                    "grammage_g_m2": row["grammage_g_m2"],
                    "required_kg": required,
                    "balance_kg": row["balance_kg"],
                    "price_rub_kg": price,
                    "cost_rub": cost,
                }
            )
        if any(
            Decimal(next(row["balance_kg"] for row in available if row["id"] == material_id))
            < required
            for material_id, required in required_by_material.items()
        ):
            continue
        candidates.append(
            {
                "layers": layers,
                "materials_cost_rub": None if price_missing else _money(total),
                "classification_verified": all(
                    row["classification_status"] == "approved" for row in (outer, medium, inner)
                ),
                "cost_comparable": not price_missing and not price_requires_verification,
                "price_warning": (
                    "В составе есть аномальная цена; она не участвует в экономическом рейтинге"
                    if price_requires_verification
                    else None
                ),
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            not row["cost_comparable"],
            row["materials_cost_rub"] is None,
            row["materials_cost_rub"] or Decimal("999999999"),
            sum(Decimal(layer["grammage_g_m2"]) for layer in row["layers"]),
        )
    )
    return {"selected": candidates[0], "alternatives": candidates[1:5]}


def add_item_costs(layout: dict, composition: dict) -> None:
    """Allocate the complete material cost of a run between ordered positions.

    Allocation follows occupied machine width, so every position carries its
    proportional share of edge trim and synchronized overproduction. Dividing
    by the ordered quantity yields the material cost of one ordered box.
    """
    total_cost = composition["materials_cost_rub"]
    used_width = Decimal(layout["used_width_mm"])
    allocated_so_far = Decimal(0)
    items = layout["items"]
    for index, item in enumerate(items):
        if total_cost is None or used_width == 0:
            item["allocated_materials_cost_rub"] = None
            item["material_cost_per_ordered_box_rub"] = None
            continue
        occupied_width = Decimal(item["stream_width_mm"] * item["streams"])
        allocated_cost = (
            Decimal(total_cost) - allocated_so_far
            if index == len(items) - 1
            else _money(Decimal(total_cost) * occupied_width / used_width)
        )
        allocated_so_far += allocated_cost
        item["allocated_materials_cost_rub"] = allocated_cost
        item["material_cost_per_ordered_box_rub"] = _money(
            allocated_cost / Decimal(item["ordered_quantity"])
        )
