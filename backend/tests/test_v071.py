from app.calc.corrugator import CorrugatorConfig, CorrugatorItem, ranked_runs
from app.calc.full import prepare_order_item, estimate_bct_mckee


def test_ranked_layout_alternatives():
    item = CorrugatorItem("A", 1599, 540, 1000, "C", "T23", 0.86346)
    variants = ranked_runs([item], [2050, 2100], CorrugatorConfig(2100, 5, 2), limit=5)
    assert len(variants) >= 2
    assert variants[0]["rank"] == 1
    assert variants[0]["is_recommended"] is True


def test_bct_mckee_is_added_for_0201():
    item = prepare_order_item({"code":"A","product_type":"0201","length_mm":450,"width_mm":326,"height_mm":210,"quantity":1000,"required_board_grade":"T23","profile":"C"})
    bct = estimate_bct_mckee(item)
    assert bct is not None
    assert bct["method"].startswith("McKee")
    assert bct["bct_estimated_kn"] > 0
    assert bct["bct_estimated_kgf"] > 0
