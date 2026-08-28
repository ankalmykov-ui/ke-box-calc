from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v2_is_not_populated_with_legacy_application_paths() -> None:
    forbidden = [ROOT / "backend", ROOT / "frontend", ROOT / "static"]
    assert all(not path.exists() for path in forbidden)


def test_pwa_assets_exist() -> None:
    required = {
        "index.html",
        "app.css",
        "app.js",
        "manifest.webmanifest",
        "sw.js",
        "icon.svg",
    }
    assert required <= {path.name for path in (ROOT / "public").iterdir()}


def test_calculation_domain_does_not_import_io_boundaries() -> None:
    calculation = ROOT / "ke_box_calc" / "domains" / "calculation"
    forbidden_tokens = ("fastapi", "psycopg", "domains.warehouse", "domains.reporting")
    for path in calculation.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden_tokens)


def test_stage_two_has_no_calculation_implementation() -> None:
    calculation_files = list((ROOT / "ke_box_calc" / "domains" / "calculation").glob("*.py"))
    assert [path.name for path in calculation_files] == ["__init__.py"]


def test_deployment_is_containerized_without_vercel_entrypoints() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "${PORT}" in dockerfile
    assert "uvicorn ke_box_calc.main:app" in dockerfile
    assert not (ROOT / "vercel.json").exists()
    assert not (ROOT / "api" / "index.py").exists()
