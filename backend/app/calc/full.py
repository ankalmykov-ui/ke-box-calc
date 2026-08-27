from __future__ import annotations

from collections import defaultdict

from .corrugator import CorrugatorConfig, CorrugatorItem, optimize_corrugator_group
from .fefco0201 import calculate_fefco0201_profile
from .grade import strongest_grade, ect_norm, normalize_grade
from .machines import select_machine
from .optimizer import Material, CompositionCandidate, rank_candidates


def prepare_order_item(item: dict) -> dict:
    product_type = str(item.get("product_type") or "0201").lower()
    quantity = int(item.get("quantity") or 0)
    if quantity <= 0:
        raise ValueError("Количество должно быть больше нуля")
    if product_type in {"0201", "fefco0201", "fefco_0201"}:
        geo = calculate_fefco0201_profile(
            float(item["length_mm"]),
            float(item["width_mm"]),
            float(item["height_mm"]),
            str(item["profile"]),
            manufacturer_joint_override_mm=item.get("manufacturer_joint_mm"),
            caliper_override_mm=item.get("caliper_mm"),
        )
        blank = geo["blank"]
        return {
            **item,
            "product_type": "FEFCO 0201",
            "quantity": quantity,
            "blank_length_mm": blank["length_mm"],
            "blank_width_mm": blank["width_mm"],
            "blank_area_m2": blank["area_m2"],
            "geometry": geo,
            "flute_direction": {
                "rule": "along_box_height",
                "label": "по высоте H",
                "box_axis": "H",
                "blank_axis": "blank_width_mm",
                "blank_dimension_mm": blank["width_mm"],
                "rotation_allowed": False,
            },
        }
    if product_type in {"sheet", "лист", "blank"}:
        a = float(item.get("blank_length_mm") or item.get("length_mm") or 0)
        b = float(item.get("blank_width_mm") or item.get("width_mm") or 0)
        if a <= 0 or b <= 0:
            raise ValueError("Для листовой заготовки нужны длина и ширина")
        return {
            **item,
            "product_type": "SHEET",
            "quantity": quantity,
            "blank_length_mm": a,
            "blank_width_mm": b,
            "blank_area_m2": round(a * b / 1_000_000, 6),
            "geometry": None,
            "flute_direction": None,
        }
    raise ValueError(f"Тип изделия {product_type} не поддерживается в v1.0")


def validate_prepared_item(item: dict, working_width_mm: float = 2100) -> dict:
    """Validate an item before BCT, layout and cost are presented as usable."""
    if working_width_mm <= 0:
        raise ValueError("Рабочая ширина гофроагрегата должна быть больше нуля")

    errors: list[dict] = []
    warnings: list[dict] = []
    processing = None
    blank_width = float(item["blank_width_mm"])

    if blank_width > working_width_mm + 1e-9:
        if item["product_type"] == "FEFCO 0201":
            message = (
                f"Гофра должна идти по высоте H, поэтому размер заготовки "
                f"{blank_width:g} мм располагается по ширине гофроагрегата "
                f"и превышает рабочую ширину {working_width_mm:g} мм."
            )
        else:
            message = (
                f"Ширина заготовки {blank_width:g} мм превышает рабочую ширину "
                f"гофроагрегата {working_width_mm:g} мм."
            )
        errors.append({"code": "corrugator_working_width", "message": message})

    if item["product_type"] == "FEFCO 0201":
        geo = item["geometry"]
        processing = select_machine(
            blank_length_mm=float(item["blank_length_mm"]),
            blank_width_mm=blank_width,
            profile=str(item.get("profile") or ""),
            caliper_mm=float(geo["profile_rule"]["caliper_mm"]),
            panels=geo["panels"],
            colors=int(item.get("colors") or 1),
            die_cut=bool(item.get("die_cut") or False),
            quantity=int(item["quantity"]),
            hourly_cost_rub=None,
        )
        recommended = processing.get("recommended")
        if recommended is None:
            errors.append({
                "code": "processing_machine_format",
                "message": (
                    f"Заготовка {item['blank_length_mm']:g}×{blank_width:g} мм "
                    "не проходит ни на одной перерабатывающей машине из справочника."
                ),
                "machines": [
                    {
                        "code": row.get("code"),
                        "name": row.get("name"),
                        "reasons": row.get("reasons") or [],
                    }
                    for row in processing.get("excluded") or []
                ],
            })
        else:
            for message in recommended.get("warnings") or []:
                warnings.append({"code": "machine_reference", "message": message})

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "prepared_item": item,
        "processing": processing,
    }


def estimate_bct_mckee(item: dict) -> dict | None:
    """Engineering BCT estimate for FEFCO 0201 using exponent McKee."""
    if item.get("product_type") != "FEFCO 0201" or not item.get("geometry"):
        return None
    grade = normalize_grade(item.get("required_board_grade")) or str(item.get("required_board_grade") or "")
    ect = ect_norm(grade)
    if ect is None:
        return {
            "method": "McKee exponent",
            "ect_min_kn_m": None,
            "bct_estimated_kn": None,
            "warning": "Для указанной марки нет нормативного ECT.",
        }

    length_m = float(item.get("length_mm") or 0) / 1000
    width_m = float(item.get("width_mm") or 0) / 1000
    height_m = float(item.get("height_mm") or 0) / 1000
    caliper_m = float(item["geometry"]["profile_rule"]["caliper_mm"]) / 1000
    perimeter_m = 2 * (length_m + width_m)
    if perimeter_m <= 0 or caliper_m <= 0:
        return None

    bct_kn = 5.87 * float(ect) * (caliper_m ** 0.508) * (perimeter_m ** 0.492)
    warnings = []
    if height_m > 0 and height_m < perimeter_m / 7:
        warnings.append("Низкая коробка: H < P/7, оценку McKee применять с осторожностью.")

    return {
        "label": "Расчётный BCT",
        "method": "McKee exponent / ASTM D5639",
        "required_grade": grade,
        "normative_ect_kn_m": round(float(ect), 4),
        "caliper_mm": round(caliper_m * 1000, 4),
        "inside_perimeter_mm": round(perimeter_m * 1000, 3),
        "bct_estimated_kn": round(bct_kn, 3),
        "bct_estimated_kgf": round(bct_kn * 101.971621, 1),
        "warning": " ".join(warnings) if warnings else None,
    }


def full_calculation(
    order_items: list[dict],
    roll_widths_mm: list[float],
    materials: list[Material] | None = None,
    composition_candidates: list[CompositionCandidate] | None = None,
    machine_hourly_costs: dict[str, float] | None = None,
    corrugator_config: CorrugatorConfig | None = None,
    other_waste_pct: float = 0,
) -> dict:
    corrugator_config = corrugator_config or CorrugatorConfig()
    prepared = [prepare_order_item(x) for x in order_items]
    validation_errors = []
    for item in prepared:
        validation = validate_prepared_item(item, corrugator_config.working_width_mm)
        validation_errors.extend(
            f"{item.get('code') or 'Позиция'}: {row['message']}"
            for row in validation["errors"]
        )
    if validation_errors:
        raise ValueError(" ".join(validation_errors))

    for item in prepared:
        item["strength"] = estimate_bct_mckee(item)

    machine_hourly_costs = machine_hourly_costs or {}
    materials = materials or []
    composition_candidates = composition_candidates or []

    by_profile: dict[str, list[dict]] = defaultdict(list)
    for x in prepared:
        by_profile[str(x.get("profile") or "").upper()].append(x)

    corrugator_groups = []
    material_total = 0.0
    composition_missing = False
    for profile, rows in sorted(by_profile.items()):
        citems = [
            CorrugatorItem(
                code=str(x.get("code") or x.get("external_ref") or f"ITEM-{idx + 1}"),
                blank_length_mm=float(x["blank_length_mm"]),
                blank_width_mm=float(x["blank_width_mm"]),
                quantity=int(x["quantity"]),
                profile=profile,
                required_board_grade=str(x.get("required_board_grade") or ""),
                blank_area_m2=float(x["blank_area_m2"]),
            )
            for idx, x in enumerate(rows)
        ]
        plan = optimize_corrugator_group(citems, roll_widths_mm, corrugator_config)

        for launch in plan["launches"]:
            item_codes = {d["code"] for d in launch["items"]}
            grade = strongest_grade(
                [
                    x.get("required_board_grade", "")
                    for x in rows
                    if str(x.get("code") or x.get("external_ref") or "") in item_codes
                ]
            )
            if grade is None:
                grade = strongest_grade([x.get("required_board_grade", "") for x in rows])

            gross_area = launch["roll_width_mm"] / 1000 * launch["run_length_m"]
            comp = (
                rank_candidates(
                    candidates=composition_candidates,
                    materials=materials,
                    required_board_grade=grade or "",
                    profile=profile,
                    net_area_m2=gross_area,
                    quantity=1,
                    edge_trim_pct=0,
                    other_waste_pct=other_waste_pct,
                )
                if materials and composition_candidates and grade
                else None
            )
            launch["target_board_grade"] = grade
            launch["gross_board_area_m2"] = round(gross_area, 4)
            launch["composition_selection"] = comp
            if comp and comp.get("recommended"):
                material_total += float(comp["recommended"]["calculation"]["total_cost_rub"])
            else:
                composition_missing = True

        corrugator_groups.append({"profile": profile, **plan})

    processing = []
    conversion_total = 0.0
    conversion_incomplete = False
    for x in prepared:
        if x["product_type"] != "FEFCO 0201":
            processing.append(
                {"code": x.get("code"), "product_type": x["product_type"], "machine_selection": None}
            )
            continue

        geo = x["geometry"]
        selection = select_machine(
            blank_length_mm=float(x["blank_length_mm"]),
            blank_width_mm=float(x["blank_width_mm"]),
            profile=str(x.get("profile") or ""),
            caliper_mm=float(geo["profile_rule"]["caliper_mm"]),
            panels=geo["panels"],
            colors=int(x.get("colors") or 1),
            die_cut=bool(x.get("die_cut") or False),
            quantity=int(x["quantity"]),
            hourly_cost_rub=None,
        )

        if machine_hourly_costs:
            from .machines import load_equipment_reference, evaluate_machine

            evals = []
            for m in load_equipment_reference()["machines"]:
                ev = evaluate_machine(
                    m,
                    float(x["blank_length_mm"]),
                    float(x["blank_width_mm"]),
                    str(x.get("profile") or ""),
                    float(geo["profile_rule"]["caliper_mm"]),
                    geo["panels"],
                    int(x.get("colors") or 1),
                    bool(x.get("die_cut") or False),
                    int(x["quantity"]),
                    machine_hourly_costs.get(m["code"]),
                )
                evals.append(ev)
            feasible = [e for e in evals if e["feasible"]]
            feasible.sort(
                key=lambda e: (
                    e["conversion_cost_rub"] is None,
                    e["conversion_cost_rub"] or 10**18,
                    e["total_minutes"] or 10**18,
                )
            )
            selection = {
                "recommended": feasible[0] if feasible else None,
                "alternatives": feasible[1:],
                "all_machines": evals,
                "excluded": [e for e in evals if not e["feasible"]],
            }

        rec = selection.get("recommended")
        if rec and rec.get("conversion_cost_rub") is not None:
            conversion_total += float(rec["conversion_cost_rub"])
        elif rec:
            conversion_incomplete = True

        processing.append(
            {"code": x.get("code"), "product_type": x["product_type"], "machine_selection": selection}
        )

    net_order_area = sum(float(x["blank_area_m2"]) * int(x["quantity"]) for x in prepared)
    known_components = []
    if not composition_missing:
        known_components.append(material_total)
    if not conversion_incomplete:
        known_components.append(conversion_total)
    total_known = sum(known_components) if known_components else None

    return {
        "version": "0.9.0-dev",
        "items": prepared,
        "corrugator": corrugator_groups,
        "processing": processing,
        "cost": {
            "net_order_area_m2": round(net_order_area, 3),
            "material_cost_rub": round(material_total, 2) if not composition_missing else None,
            "conversion_cost_rub": round(conversion_total, 2) if not conversion_incomplete else None,
            "known_total_cost_rub": round(total_known, 2) if total_known is not None else None,
            "full_cost_complete": not composition_missing and not conversion_incomplete,
            "notes": [
                "Материальная стоимость считается по площади фактического полотна выбранного раскроя, включая краевую обрезь и перепроизводство.",
                "Нормативный ECT и фактический ECT являются разными сущностями; отдельный «расчётный ECT» не используется.",
                "Полная себестоимость закрывается после применения утверждённых композиций, складских цен и тарифов перерабатывающих линий.",
            ],
        },
        "snapshot": {
            "geometry": "FEFCO0201 source-priority v0.4-final",
            "corrugator": "optimizer v0.8 / two crosscut levels",
            "equipment": "equipment reference v0.8",
            "grade_norms": "board grade norms v0.6",
            "bct": "McKee exponent / versioned base implementation",
        },
    }
