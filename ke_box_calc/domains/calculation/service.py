from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def calculate_first_variant(
    *,
    length_mm: int,
    width_mm: int,
    height_mm: int,
    quantity: int,
    materials: list[dict],
    technological_trim_mm: int,
) -> dict:
    if len(materials) != 3:
        raise ValueError("Первый запуск поддерживает трёхслойный картон: 3 слоя сырья")

    blank_across_mm = height_mm + width_mm
    blank_machine_mm = 2 * (length_mm + width_mm) + 40 + technological_trim_mm
    effective_web_mm = min(row["width_mm"] for row in materials)
    lanes = effective_web_mm // blank_across_mm
    if lanes < 1:
        return {
            "status": "blocked",
            "reason": "Заготовка шире доступной ширины выбранного сырья",
            "geometry": {
                "blank_across_mm": blank_across_mm,
                "blank_machine_mm": blank_machine_mm,
                "effective_web_mm": effective_web_mm,
            },
        }

    produced_per_cut = lanes
    cuts = (quantity + produced_per_cut - 1) // produced_per_cut
    produced_quantity = cuts * produced_per_cut
    run_length_m = Decimal(cuts * blank_machine_mm) / Decimal(1000)
    web_area_m2 = Decimal(effective_web_mm) / Decimal(1000) * run_length_m
    useful_area_m2 = (
        Decimal(blank_across_mm * blank_machine_mm * quantity) / Decimal(1_000_000)
    )
    trim_area_m2 = web_area_m2 - useful_area_m2
    trim_percent = (trim_area_m2 / web_area_m2 * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    layers = []
    total_cost = Decimal(0)
    missing: list[str] = []
    for index, row in enumerate(materials):
        coefficient = Decimal("1.43") if index == 1 else Decimal(1)
        required_kg = (
            web_area_m2 * Decimal(row["grammage_g_m2"]) * coefficient / Decimal(1000)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        price = row["price_rub_kg"]
        layer_cost = None if price is None else required_kg * price
        if price is None:
            missing.append(f"Нет действующей цены: {row['name']}")
        if Decimal(row["balance_kg"]) < required_kg:
            missing.append(f"Недостаточный остаток: {row['name']}")
        if layer_cost is not None:
            total_cost += layer_cost
        layers.append(
            {
                "material_id": row["id"],
                "name": row["name"],
                "required_kg": required_kg,
                "balance_kg": row["balance_kg"],
                "price_rub_kg": price,
                "cost_rub": layer_cost,
            }
        )

    status = "feasible_priced" if not missing else "feasible_incomplete"
    return {
        "status": status,
        "missing": missing,
        "geometry": {
            "blank_across_mm": blank_across_mm,
            "blank_machine_mm": blank_machine_mm,
            "effective_web_mm": effective_web_mm,
            "lanes": lanes,
            "cuts": cuts,
            "produced_quantity": produced_quantity,
            "run_length_m": run_length_m.quantize(Decimal("0.01")),
            "web_area_m2": web_area_m2.quantize(Decimal("0.01")),
            "trim_area_m2": trim_area_m2.quantize(Decimal("0.01")),
            "trim_percent": trim_percent,
        },
        "layers": layers,
        "cost": {
            "materials_total_rub": total_cost.quantize(Decimal("0.01")),
            "per_box_rub": (total_cost / quantity).quantize(Decimal("0.01")),
            "complete": not missing,
        },
        "strength": {
            "bct": None,
            "status": "missing_laboratory_or_approved_ect",
            "message": (
                "BCT не подменяется предположением: нужна утверждённая "
                "композиция и ECT/лаборатория"
            ),
        },
    }
