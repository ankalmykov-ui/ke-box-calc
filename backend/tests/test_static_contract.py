from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_api_response_body_is_read_only_once():
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "const body = await r.text()" in app_js
    assert "await r.json()" not in app_js


def test_service_worker_does_not_cache_api_or_failed_responses():
    service_worker = (STATIC / "sw.js").read_text(encoding="utf-8")
    assert 'url.pathname.startsWith("/api/")' in service_worker
    assert "if(r.ok)" in service_worker


def test_order_view_has_bottom_calculate_and_no_inert_planning_fields():
    index_html = (STATIC / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert index_html.count("calculate-order-btn") == 2
    assert "Рассчитать заказ" in index_html
    assert "Горизонт групповой оптимизации" not in index_html
    assert "Прочие технологические потери" not in index_html
    assert 'api("/api/validate/item"' in app_js
    assert "Направление гофры" in app_js
