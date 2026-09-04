from fastapi.testclient import TestClient

from ke_box_calc.main import app

client = TestClient(app)


def test_root_identifies_automatic_calculation() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Рассчитать автоматически" in response.text
    assert "один или несколько коробов" in response.text


def test_v2_meta_contract() -> None:
    response = client.get("/api/v2/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v2"
    assert body["stage"] == 4
    assert body["calculation_engine"] == "automatic_stock_optimizer"
    assert body["database"]["schema_min"] == "2.0.0"
    assert body["database"]["known_migrations"] == [
        "0001_identity_scope",
        "0002_materials_warehouse",
        "0003_calculation_references",
        "0004_price_quality",
        "0005_laboratory_bct_policy",
    ]


def test_materials_require_database() -> None:
    assert client.get("/api/v2/materials").status_code == 503


def test_liveness_and_optional_local_database_readiness() -> None:
    assert client.get("/api/v2/health/live").status_code == 200
    ready = client.get("/api/v2/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "not_required"


def test_openapi_is_versioned() -> None:
    response = client.get("/api/v2/openapi.json")
    assert response.status_code == 200
    assert "/api/v2/meta" in response.json()["paths"]
    assert "/api/v2/materials/import-opening-balance" in response.json()["paths"]


def test_opening_balance_import_rejects_invalid_checksum_before_database() -> None:
    response = client.post(
        "/api/v2/materials/import-opening-balance",
        json={
            "source_name": "Тестовый остаток",
            "source_checksum": "not-a-checksum",
            "items": [
                {
                    "name": "Бумага 140 2100",
                    "material_type": "paper",
                    "grammage_g_m2": 140,
                    "width_mm": 2100,
                    "quantity_kg": 100,
                    "price_rub_kg": 50,
                }
            ],
        },
    )
    assert response.status_code == 422
