from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ke_box_calc.domains.calculation.optimizer import (
    OrderItem,
    choose_composition,
    plan_launches,
)


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
    useful_area_m2 = Decimal(blank_across_mm * blank_machine_mm * quantity) / Decimal(1_000_000)
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
                "BCT не подменяется предположением: нужна утверждённая композиция и ECT/лаборатория"
            ),
        },
    }


def _round_mm(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_fefco_0201_geometry(
    *,
    length_mm: int,
    width_mm: int,
    height_mm: int,
    profile: str,
    technological_trim_mm: int,
    references: dict,
) -> dict:
    profile_key = profile.upper().replace("Е", "E").replace("В", "B").replace("С", "C")
    profile_data = references["profiles"]["payload"].get(profile_key)
    if not profile_data:
        raise ValueError(f"Неизвестный профиль: {profile}")
    d = Decimal(str(profile_data["caliper_mm"]))
    joint = Decimal(str(references["fefco_0201"]["payload"]["manufacturer_joint_mm"]))
    l1 = _round_mm(Decimal(length_mm))
    b1 = _round_mm(Decimal(width_mm) + d)
    l2 = _round_mm(Decimal(length_mm) + d)
    b2 = _round_mm(Decimal(width_mm) + d / 2)
    body = _round_mm(Decimal(height_mm) + d)
    first_flap = width_mm // 2
    second_flap = width_mm - first_flap
    production_development = l1 + b1 + l2 + b2 + _round_mm(joint)
    return {
        "profile": profile_key,
        "caliper_mm": d,
        "panels_mm": {"l1": l1, "b1": b1, "l2": l2, "b2": b2},
        "manufacturer_joint_mm": _round_mm(joint),
        "glue_gap_changed": False,
        "flaps_mm": {"top": first_flap, "bottom": second_flap, "body": body},
        "blank_length_mm": production_development + technological_trim_mm,
        "blank_width_mm": first_flap + body + second_flap,
        "technological_trim_mm": technological_trim_mm,
        "flute_direction": {"box_axis": "H", "rotation_allowed": False},
    }


def _estimate_bct(item: dict, references: dict) -> dict:
    ect = references.get("board_grades", {}).get("payload", {}).get(item["board_grade"])
    if ect is None:
        return {
            "calculated_kn": None,
            "actual_kn": None,
            "message": "Для марки нет нормативного ECT",
        }
    perimeter_m = Decimal(2 * (item["length_mm"] + item["width_mm"])) / Decimal(1000)
    caliper_m = Decimal(item["geometry"]["caliper_mm"]) / Decimal(1000)
    calculated = (
        Decimal("5.87")
        * Decimal(str(ect))
        * (caliper_m ** Decimal("0.508"))
        * (perimeter_m ** Decimal("0.492"))
    )
    return {
        "calculated_kn": calculated.quantize(Decimal("0.001")),
        "actual_kn": None,
        "normative_ect_kn_m": ect,
        "message": "Расчётный BCT; фактических сопоставимых испытаний в базе пока нет",
    }


def calculate_order_automatically(
    *, items: list[dict], materials: list[dict], references: dict
) -> dict:
    corrugator = references["corrugator"]["payload"]
    prepared = []
    for index, source in enumerate(items, start=1):
        geometry = calculate_fefco_0201_geometry(
            length_mm=source["length_mm"],
            width_mm=source["width_mm"],
            height_mm=source["height_mm"],
            profile=source["profile"],
            technological_trim_mm=source.get("technological_trim_mm", 0),
            references=references,
        )
        row = {**source, "code": source.get("code") or f"BOX-{index:03d}", "geometry": geometry}
        row["strength"] = _estimate_bct(row, references)
        prepared.append(row)

    widths_with_liner = {
        int(row["width_mm"]) for row in materials if row["material_type"] == "liner"
    }
    widths_with_medium = {
        int(row["width_mm"]) for row in materials if row["material_type"] == "paper"
    }
    roll_widths = sorted(
        width
        for width in widths_with_liner & widths_with_medium
        if width <= corrugator["working_width_mm"]
    )
    optimizer_items = [
        OrderItem(
            code=row["code"],
            blank_length_mm=row["geometry"]["blank_length_mm"],
            blank_width_mm=row["geometry"]["blank_width_mm"],
            quantity=row["quantity"],
            profile=row["geometry"]["profile"],
            board_grade=row["board_grade"],
        )
        for row in prepared
    ]
    plan = plan_launches(optimizer_items, roll_widths, corrugator)
    launches = []
    any_unverified = False
    for launch_number, launch in enumerate(plan["launches"], start=1):
        flute_factor = Decimal(
            str(references["profiles"]["payload"][launch["profile"]]["flute_factor"])
        )
        options = []
        for layout in launch["layouts"]:
            composition = choose_composition(layout, materials, flute_factor)
            if composition is None:
                continue
            selected = composition["selected"]
            # A classified material is necessary, but not sufficient. The exact
            # layer recipe must also exist in the approved composition catalogue.
            # That catalogue has not been loaded yet, so grade matching stays open.
            verified = False
            any_unverified = any_unverified or not verified
            option = {
                **layout,
                "composition": selected,
                "composition_alternatives": composition["alternatives"],
                "status": "feasible_incomplete",
                "missing": ([] if verified else ["Состав сырья ещё не утверждён технологом"])
                + ["Нет фактического BCT по сопоставимой композиции"],
            }
            options.append(option)
        options.sort(
            key=lambda row: (
                row["composition"]["materials_cost_rub"] is None,
                row["composition"]["materials_cost_rub"] or Decimal("999999999"),
                row["total_waste_m2"],
                row["run_length_m"],
            )
        )
        for rank, option in enumerate(options[:5], start=1):
            option["algorithm_rank"] = rank
            option["is_recommended"] = rank == 1 and option["status"] == "feasible_priced"
            option["is_preliminary_leader"] = rank == 1
        if not options:
            any_unverified = True
        launches.append(
            {"launch_number": launch_number, "profile": launch["profile"], "options": options[:5]}
        )

    return {
        "status": "feasible_incomplete"
        if any_unverified or plan["unplanned"]
        else "feasible_priced",
        "recommendation_available": not any_unverified
        and not plan["unplanned"]
        and all(launch["options"] for launch in launches),
        "items": prepared,
        "launches": launches,
        "unplanned": plan["unplanned"],
        "warnings": [
            (
                "Склад загружен как предварительный: варианты можно сравнивать по "
                "раскрою и цене, но нельзя утверждать как производственную "
                "композицию до классификации сырья."
            ),
            "Коэффициент гофрирования и нормативы марок требуют подтверждения технологом.",
        ]
        if any_unverified
        else [],
        "reference_versions": {
            code: {"version": data["version"], "status": data["status"]}
            for code, data in references.items()
        },
    }
