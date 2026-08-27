from dataclasses import dataclass


@dataclass(frozen=True)
class PaperLayer:
    role: str
    gsm: float
    price_rub_t: float
    corrugation_coefficient: float = 1.0
    material_name: str | None = None


def calculate_composition(
    net_area_m2: float,
    quantity: int,
    layers: list[PaperLayer],
    edge_trim_pct: float = 0.0,
    other_waste_pct: float = 0.0,
) -> dict:
    if net_area_m2 <= 0 or quantity <= 0:
        raise ValueError("Area and quantity must be greater than zero")
    if not layers:
        raise ValueError("At least one paper layer is required")
    if not (0 <= edge_trim_pct < 100) or not (0 <= other_waste_pct < 100):
        raise ValueError("Waste percentages must be in [0, 100)")

    total_net_area = net_area_m2 * quantity
    # Edge trim is a loss of web width. To obtain gross web area from net useful area,
    # divide by the retained fraction rather than simply adding the percentage.
    gross_web_area = total_net_area / (1 - edge_trim_pct / 100)
    gross_with_other_waste = gross_web_area / (1 - other_waste_pct / 100)

    layer_results = []
    total_mass_kg = 0.0
    total_cost_rub = 0.0
    effective_kg_m2 = 0.0

    for layer in layers:
        if layer.gsm <= 0 or layer.price_rub_t < 0 or layer.corrugation_coefficient <= 0:
            raise ValueError("Invalid layer parameters")

        kg_m2 = layer.gsm * layer.corrugation_coefficient / 1000
        mass_kg = gross_with_other_waste * kg_m2
        cost_rub = mass_kg * layer.price_rub_t / 1000

        effective_kg_m2 += kg_m2
        total_mass_kg += mass_kg
        total_cost_rub += cost_rub
        layer_results.append(
            {
                "role": layer.role,
                "material_name": layer.material_name,
                "gsm": layer.gsm,
                "corrugation_coefficient": layer.corrugation_coefficient,
                "effective_kg_m2": round(kg_m2, 6),
                "mass_kg": round(mass_kg, 3),
                "price_rub_t": round(layer.price_rub_t, 2),
                "cost_rub": round(cost_rub, 2),
            }
        )

    return {
        "net_area_m2": round(total_net_area, 6),
        "gross_web_area_m2": round(gross_web_area, 6),
        "gross_area_with_other_waste_m2": round(gross_with_other_waste, 6),
        "edge_trim_pct": edge_trim_pct,
        "other_waste_pct": other_waste_pct,
        "effective_board_mass_kg_m2": round(effective_kg_m2, 6),
        "layers": layer_results,
        "total_mass_kg": round(total_mass_kg, 3),
        "total_cost_rub": round(total_cost_rub, 2),
        "cost_rub_m2_net": round(total_cost_rub / total_net_area, 4),
    }
