from decimal import Decimal
from io import BytesIO
from pathlib import Path
import zipfile

import pytest
from pydantic import ValidationError

from app.compositions.models import (
    BctResultCreate,
    CompositionCreate,
    CompositionLayerInput,
)
from app.db import REQUIRED_SCHEMA_VERSION, schema_status
from app.db_migrations import migration_files, should_apply_migrations_on_startup
from app.main import APP_VERSION, app, health
from app.importers.inventory_1c import parse_inventory_import
from app.warehouse.models import (
    MaterialPriceInput,
    ReceiptLineInput,
    StockQuantityInput,
)


BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "migrations" / "0001_v0_9_foundation.sql"
COMPOSITION_MIGRATION = BACKEND / "migrations" / "0002_v0_9_compositions.sql"
PRICE_MIGRATION = BACKEND / "migrations" / "0003_v0_9_material_prices.sql"
SERVICE = BACKEND / "app" / "warehouse" / "service.py"
COMPOSITION_SERVICE = BACKEND / "app" / "compositions" / "service.py"


def test_v09_version_and_database_are_lazy(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert APP_VERSION == "0.9.0-dev"
    assert health()["database"] == "not_configured"
    assert schema_status() == {
        "status": "not_configured",
        "required_version": REQUIRED_SCHEMA_VERSION,
        "applied_versions": [],
    }


def test_preview_auto_migrations_are_explicitly_gated(monkeypatch):
    monkeypatch.delenv("AUTO_APPLY_MIGRATIONS", raising=False)
    assert should_apply_migrations_on_startup() is False

    monkeypatch.setenv("AUTO_APPLY_MIGRATIONS", "true")
    assert should_apply_migrations_on_startup() is True

    source = (BACKEND / "app" / "db_migrations.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in source
    assert "MIGRATION_LOCK_KEY" in source


def test_first_migration_is_discoverable_and_canonical():
    files = migration_files()
    assert [path.stem for path in files] == [
        "0001_v0_9_foundation",
        "0002_v0_9_compositions",
        REQUIRED_SCHEMA_VERSION,
    ]
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "organizations",
        "sites",
        "warehouses",
        "materials",
        "material_external_identifiers",
        "material_widths",
        "material_lots",
        "material_rolls",
        "stock_documents",
        "stock_movements",
        "inventory_documents",
        "inventory_lines",
        "writeoff_transactions",
        "audit_log",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    assert "CREATE OR REPLACE VIEW stock_balances" in sql
    assert "SUM(base_quantity_kg)" in sql
    assert "UNIQUE (organization_id, idempotency_key)" in sql
    assert "ALTER TABLE import_batches RENAME TO import_batches_v08_legacy" in sql
    assert "FOREIGN KEY (material_id, organization_id)" in sql
    assert "external_code" in sql
    assert "code_1c TEXT NOT NULL" not in sql


def test_writeoff_contract_is_atomic_and_separate_from_pdf():
    service = SERVICE.read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in service
    assert "Недостаточный остаток" in service
    assert "idempotent_replay" in service
    assert "Рулон уже зарегистрирован поступлением" in service

    openapi = app.openapi()
    paths = openapi["paths"]
    assert "/api/v1/stock/writeoffs/confirm" in paths
    assert "/api/v1/stock/writeoffs/{document_id}/reverse" in paths
    assert "/api/v1/stock/receipts" in paths
    assert paths["/api/import/1c/materials/preview"]["post"]["deprecated"] is True
    assert "/api/v1/inventory/imports/1c/preview" in paths


def test_material_prices_are_versioned_and_exposed_by_api():
    sql = PRICE_MIGRATION.read_text(encoding="utf-8")
    assert "idx_material_price_history_current" in sql
    assert "material_price_history_is_immutable" in sql

    paths = app.openapi()["paths"]
    assert "/api/v1/organizations" in paths
    assert "/api/v1/materials/{material_id}/prices" in paths


def test_material_price_period_must_be_ordered():
    with pytest.raises(ValidationError):
        MaterialPriceInput(
            price_per_unit=Decimal("47000"),
            valid_from="2026-08-28T00:00:00+03:00",
            valid_to="2026-08-27T00:00:00+03:00",
            recorded_by="test",
        )


def test_inventory_docx_is_preview_only_and_preserves_accounting_anomalies():
    def row(*values: str) -> str:
        cells = "".join(
            f"<w:tc><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:tc>"
            for value in values
        )
        return f"<w:tr>{cells}</w:tr>"

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:tbl>"
        + row("Склад", "Количество", "Цена", "Стоимость")
        + row("Основной склад", "1200,000", "56,12", "67344,00")
        + row("Бумага 90 2100 Б-люкс", "1200,000", "-1,50", "-1800,00")
        + row("Картон Белый лайнер Илим 110/2050", "", "95,64", "0,00")
        + row("Итого", "1200,000", "", "")
        + "</w:tbl></w:body></w:document>"
    )
    content = BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("word/document.xml", document)

    result = parse_inventory_import(content.getvalue(), "inventory.docx")
    assert result["can_apply"] is False
    assert result["source_role"] == "inventory_reference_only"
    assert result["stats"] == {
        "rows_total": 2,
        "rows_ready": 0,
        "rows_warning": 1,
        "rows_error": 1,
        "missing_quantity": 1,
        "negative_price": 1,
        "warehouses": ["Основной склад"],
        "calculated_total_kg": 1200.0,
        "reported_total_kg": 1200.0,
        "totals_match": True,
    }
    assert result["rows"][0]["material_type"] == "fluting"
    assert result["rows"][0]["gsm"] == 90.0
    assert result["rows"][0]["roll_width_mm"] == 2100.0
    assert result["rows"][1]["material_type"] == "liner"
    assert result["rows"][1]["gsm"] == 110.0
    assert result["rows"][1]["roll_width_mm"] == 2050.0


def test_non_kg_quantity_requires_explicit_conversion():
    with pytest.raises(ValidationError):
        StockQuantityInput(quantity=10, unit_code="m")

    quantity = StockQuantityInput(
        quantity=Decimal("10"),
        unit_code="m",
        base_quantity_kg=Decimal("27.5"),
    )
    assert quantity.base_quantity_kg == Decimal("27.5")


def test_kg_quantity_uses_itself_as_base_quantity():
    quantity = StockQuantityInput(quantity=Decimal("12.25"), unit_code="kg")
    assert quantity.base_quantity_kg == Decimal("12.25")


def test_receipt_roll_requires_width():
    with pytest.raises(ValidationError):
        ReceiptLineInput(
            material_id="00000000-0000-0000-0000-000000000001",
            lot_code="LOT-1",
            roll_code="ROLL-1",
            quantity=100,
        )


def test_composition_schema_keeps_bct_and_cost_history_separate():
    sql = COMPOSITION_MIGRATION.read_text(encoding="utf-8")
    for table in (
        "composition_definitions",
        "composition_versions",
        "composition_layers",
        "composition_bct_results",
        "composition_cost_snapshots",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "result_kind IN ('calculated', 'actual')" in sql
    assert "total_cost_rub_m2" in sql
    assert "version_no" in sql
    assert "prevent_immutable_history_mutation" in sql
    assert "stock_movements_are_immutable" in sql


def test_composition_api_is_versioned_and_independent_from_warehouse():
    paths = app.openapi()["paths"]
    assert "/api/v1/compositions" in paths
    assert "/api/v1/compositions/{definition_id}/versions" in paths
    assert "/api/v1/composition-versions/{version_id}/bct-results" in paths
    assert "/api/v1/composition-versions/{version_id}/cost-snapshots" in paths


def test_optional_composition_filters_have_explicit_postgres_types():
    service = COMPOSITION_SERVICE.read_text(encoding="utf-8")
    assert service.count("%s::text IS NULL") == 2
    assert "upper(%s::text)" in service


def test_composition_layers_must_be_contiguous_and_three_or_five():
    layers = [
        CompositionLayerInput(
            layer_no=index,
            layer_role=f"layer-{index}",
            material_id=f"00000000-0000-0000-0000-{index:012d}",
        )
        for index in (1, 2, 4)
    ]
    with pytest.raises(ValidationError):
        CompositionCreate(
            organization_id="00000000-0000-0000-0000-000000000100",
            code="COMP-1",
            name="Тест",
            board_grade_code="T23",
            profile_code="C",
            created_by="test",
            layers=layers,
        )


def test_calculated_bct_requires_versioned_method():
    with pytest.raises(ValidationError):
        BctResultCreate(
            result_kind="calculated",
            bct_kn=Decimal("4.5"),
            source_system="ke-box-calc",
            recorded_by="test",
        )

    result = BctResultCreate(
        result_kind="calculated",
        bct_kn=Decimal("4.5"),
        method_code="mckee",
        method_version="1.0",
        source_system="ke-box-calc",
        recorded_by="test",
    )
    assert result.bct_kn == Decimal("4.5")
