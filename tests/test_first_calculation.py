from decimal import Decimal
from uuid import UUID

from ke_box_calc.domains.calculation.service import calculate_first_variant


def _material(index: int, *, width: int = 2100, price: str = "50") -> dict:
    return {
        "id": UUID(int=index),
        "name": f"Материал {index}",
        "grammage_g_m2": Decimal("140"),
        "width_mm": width,
        "balance_kg": Decimal("10000"),
        "price_rub_kg": Decimal(price),
    }


def test_first_variant_reports_geometry_cost_and_honest_missing_bct() -> None:
    result = calculate_first_variant(
        length_mm=400,
        width_mm=300,
        height_mm=250,
        quantity=1000,
        materials=[_material(1), _material(2), _material(3)],
        technological_trim_mm=0,
    )
    assert result["status"] == "feasible_priced"
    assert result["geometry"]["lanes"] == 3
    assert result["geometry"]["trim_percent"] > 0
    assert result["cost"]["materials_total_rub"] > 0
    assert result["strength"]["bct"] is None


def test_first_variant_blocks_sheet_wider_than_material() -> None:
    result = calculate_first_variant(
        length_mm=400,
        width_mm=1300,
        height_mm=1000,
        quantity=100,
        materials=[_material(1, width=2000), _material(2), _material(3)],
        technological_trim_mm=0,
    )
    assert result["status"] == "blocked"
