import json

from app.calc.full import prepare_order_item, estimate_bct_mckee
from app.calc.machines import evaluate_machine, load_equipment_reference
from app.calc.optimizer import Material
from app.main import FullCalculationRequest, MaterialRequest, OrderItemRequest, calc_full


def test_control_card_990_geometry_is_preserved():
    item = prepare_order_item({
        "code": "990",
        "product_type": "0201",
        "length_mm": 450,
        "width_mm": 326,
        "height_mm": 210,
        "quantity": 1,
        "required_board_grade": "T23.1",
        "profile": "C",
    })
    assert item["blank_length_mm"] == 1599
    assert item["blank_width_mm"] == 540


def test_bct_uses_normative_ect_label_only():
    item = prepare_order_item({
        "code": "A",
        "product_type": "0201",
        "length_mm": 450,
        "width_mm": 326,
        "height_mm": 210,
        "quantity": 1,
        "required_board_grade": "T23.1",
        "profile": "C",
    })
    bct = estimate_bct_mckee(item)
    assert bct["label"] == "Расчётный BCT"
    assert bct["normative_ect_kn_m"] == 3.8
    assert "calculated_ect" not in bct


def test_material_keeps_roll_width_and_1c_metadata():
    material = Material(
        code_1c="PAPER-1",
        variant_1c="W2150",
        name="Test paper",
        gsm=140,
        price_rub_t=50000,
        roll_width_mm=2150,
        manufacturer="Test Mill",
        material_type="liner",
    )
    assert material.roll_width_mm == 2150
    assert material.key == "PAPER-1::W2150"


def test_flaps_mm_reference_is_actually_checked():
    machine = {
        "code": "T",
        "name": "Test",
        "profiles": ["C"],
        "colors": 1,
        "sheet": {"min_a_mm": 1, "min_b_mm": 1, "max_a_mm": 5000, "max_b_mm": 5000},
        "board_thickness_mm": {"min": 1, "max": 10},
        "flaps_mm": {"small_min": 200, "small_max": 500, "large_min": 200, "large_max": 500},
        "speed": {"cruise_per_hour": 1000},
        "setup_minutes": 0,
        "status": "passport_confirmed",
    }
    result = evaluate_machine(
        machine,
        blank_length_mm=1000,
        blank_width_mm=600,
        profile="C",
        caliper_mm=4,
        panels={"top_flap_mm": 150, "bottom_flap_mm": 150},
    )
    assert result["feasible"] is False
    assert any("Малый клапан" in x for x in result["reasons"])


def test_toprint_reference_is_version_08_family_data():
    data = load_equipment_reference()
    assert data["version"] == "0.8"
    top = next(x for x in data["machines"] if x["code"] == "M002")
    assert top["model"] == "TP-CR-0924"
    assert top["sheet"]["max_a_mm"] == 900
    assert top["sheet"]["max_b_mm"] == 2400
    assert top["speed"]["mechanical_max_per_hour"] == 18000
    assert top["status"] == "catalog_family_unverified"


def test_roll_widths_can_be_derived_from_active_1c_materials():
    req = FullCalculationRequest(
        items=[OrderItemRequest(
            code="A",
            product_type="0201",
            length_mm=450,
            width_mm=326,
            height_mm=210,
            quantity=100,
            required_board_grade="T23.1",
            profile="C",
        )],
        roll_widths_mm=[],
        materials=[MaterialRequest(
            code_1c="P1",
            name="Paper",
            gsm=140,
            price_rub_t=50000,
            roll_width_mm=2150,
            procurement_status="active",
        )],
    )
    result = calc_full(req)
    assert result["roll_width_source"] == "1c_materials"
    launches = [launch for group in result["corrugator"] for launch in group["launches"]]
    assert launches
    assert all(launch["roll_width_mm"] == 2150 for launch in launches)


def test_full_calculation_result_is_json_serializable():
    req = FullCalculationRequest(
        items=[OrderItemRequest(
            code="BOX-001",
            product_type="0201",
            length_mm=450,
            width_mm=326,
            height_mm=210,
            quantity=1000,
            required_board_grade="T23.1",
            profile="B",
        )],
        roll_widths_mm=[2150, 2100, 2050],
    )

    result = calc_full(req)
    json.dumps(result, ensure_ascii=False)

    launches = [launch for group in result["corrugator"] for launch in group["launches"]]
    assert launches
    assert all(launch not in launch["layout_alternatives"] for launch in launches)
