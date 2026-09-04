from decimal import Decimal

from ke_box_calc.domains.laboratory.importer import (
    infer_profile_from_requested_grade,
    normalize_grade,
    normalize_material_name,
    parse_bct_kn,
    parse_dimensions,
    parse_layer,
    parse_measurements,
    parse_required_bct_kn,
)


def test_laboratory_bct_is_normalized_from_newtons_to_kn() -> None:
    assert parse_bct_kn(3560) == Decimal("3.560")
    assert parse_bct_kn("1817,3/1820,01/2009,99/2075,52") == Decimal("1.931")
    assert parse_measurements("1817,3/1820,01") == (
        Decimal("1817.3"),
        Decimal("1820.01"),
    )


def test_customer_requirement_parser_preserves_units() -> None:
    assert parse_required_bct_kn("ВСТ не менее 2500 Н") == Decimal("2.500")
    assert parse_required_bct_kn("3,2 кН") == Decimal("3.200")
    assert parse_required_bct_kn(3700) == Decimal("3.700")
    assert parse_required_bct_kn("Образцы") is None


def test_requested_grade_can_supply_profile_but_not_strength() -> None:
    assert normalize_grade("Т-25 С") == "T25C"
    assert infer_profile_from_requested_grade("Т-25 С") == "C"
    assert infer_profile_from_requested_grade("П-32 ВС") == "BC"
    assert infer_profile_from_requested_grade("Т-24 В") == "B"
    assert infer_profile_from_requested_grade("T23.1") is None


def test_dimensions_and_material_identity_are_normalized() -> None:
    assert parse_dimensions(" 390*192*150 ") == (390, 192, 150)
    assert parse_dimensions("1313*368") == (1313, 368)
    assert parse_dimensions("не указан") is None
    assert normalize_material_name("К-0-125 2100 Выборг") == "К 0 125 ВЫБОРГ"
    assert normalize_material_name("К-0-125 2050 Выборг") == "К 0 125 ВЫБОРГ"
    assert parse_layer("Б 140 2100 Атлас", "fluting", 2) == {
        "layer_index": 2,
        "layer_role": "fluting",
        "raw_material_name": "Б 140 2100 Атлас",
        "normalized_material_name": "Б 140 АТЛАС",
        "grammage_g_m2": Decimal("140"),
        "source_width_mm": 2100,
    }
