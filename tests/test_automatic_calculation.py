from decimal import Decimal
from uuid import UUID

from ke_box_calc.domains.calculation.service import (
    calculate_fefco_0201_geometry,
    calculate_order_automatically,
)

REFERENCES = {
    "fefco_0201": {
        "version": "test",
        "status": "working_reference",
        "payload": {"manufacturer_joint_mm": 37},
    },
    "profiles": {
        "version": "test",
        "status": "working_reference",
        "payload": {"C": {"caliper_mm": 4.02, "flute_factor": 1.47}},
    },
    "corrugator": {
        "version": "test",
        "status": "working_reference",
        "payload": {"working_width_mm": 2100, "max_streams": 5, "crosscut_levels": 2},
    },
    "board_grades": {
        "version": "test",
        "status": "requires_verification",
        "payload": {"T23.1": 3.8},
    },
}


def material(index: int, material_type: str, grammage: str, price: str) -> dict:
    return {
        "id": UUID(int=index),
        "name": f"Материал {index}",
        "material_type": material_type,
        "grammage_g_m2": Decimal(grammage),
        "width_mm": 2100,
        "balance_kg": Decimal("10000"),
        "price_rub_kg": Decimal(price),
        "classification_status": "preliminary",
    }


def test_control_card_geometry_matches_specification() -> None:
    geometry = calculate_fefco_0201_geometry(
        length_mm=450,
        width_mm=326,
        height_mm=210,
        profile="C",
        technological_trim_mm=0,
        references=REFERENCES,
    )
    assert geometry["blank_length_mm"] == 1599
    assert geometry["blank_width_mm"] == 540
    assert geometry["flute_direction"]["box_axis"] == "H"
    assert geometry["glue_gap_changed"] is False


def test_one_click_calculation_selects_layout_and_stock_composition() -> None:
    result = calculate_order_automatically(
        items=[
            {
                "code": "BOX-001",
                "length_mm": 400,
                "width_mm": 300,
                "height_mm": 250,
                "quantity": 1000,
                "board_grade": "T23.1",
                "profile": "C",
                "technological_trim_mm": 0,
            }
        ],
        materials=[
            material(1, "liner", "140", "52"),
            material(2, "paper", "125", "47"),
            material(3, "liner", "160", "60"),
        ],
        references=REFERENCES,
    )
    assert result["items"][0]["geometry"]["blank_length_mm"] > 0
    assert result["launches"][0]["options"][0]["composition"]["layers"]
    assert result["launches"][0]["options"][0]["composition"]["materials_cost_rub"] > 0
    assert result["recommendation_available"] is False
    assert result["status"] == "feasible_incomplete"


def test_two_cut_lengths_can_share_one_launch() -> None:
    items = [
        {
            "code": "A",
            "length_mm": 400,
            "width_mm": 300,
            "height_mm": 250,
            "quantity": 100,
            "board_grade": "T23.1",
            "profile": "C",
            "technological_trim_mm": 0,
        },
        {
            "code": "B",
            "length_mm": 500,
            "width_mm": 300,
            "height_mm": 250,
            "quantity": 100,
            "board_grade": "T23.1",
            "profile": "C",
            "technological_trim_mm": 0,
        },
    ]
    result = calculate_order_automatically(
        items=items,
        materials=[material(1, "liner", "140", "52"), material(2, "paper", "125", "47")],
        references=REFERENCES,
    )
    option = result["launches"][0]["options"][0]
    assert option["crosscut_levels_used"] == 2
    assert len(option["items"]) == 2
