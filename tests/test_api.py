from fastapi.testclient import TestClient

from ke_box_calc.main import app

client = TestClient(app)


def test_root_identifies_first_working_contour() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Запуск №1 · рабочий контур" in response.text
    assert "Сырьё и первый расчёт" in response.text


def test_v2_meta_contract() -> None:
    response = client.get("/api/v2/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v2"
    assert body["stage"] == 3
    assert body["calculation_engine"] == "first_variant"
    assert body["database"]["schema_min"] == "2.0.0"
    assert body["database"]["known_migrations"] == [
        "0001_identity_scope",
        "0002_materials_warehouse",
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
