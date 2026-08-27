from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db import REQUIRED_SCHEMA_VERSION, schema_status
from app.db_migrations import migration_files
from app.main import APP_VERSION, app, health
from app.warehouse.models import ReceiptLineInput, StockQuantityInput


BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "migrations" / "0001_v0_9_foundation.sql"
SERVICE = BACKEND / "app" / "warehouse" / "service.py"


def test_v09_version_and_database_are_lazy(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert APP_VERSION == "0.9.0-dev"
    assert health()["database"] == "not_configured"
    assert schema_status() == {
        "status": "not_configured",
        "required_version": REQUIRED_SCHEMA_VERSION,
        "applied_versions": [],
    }


def test_first_migration_is_discoverable_and_canonical():
    files = migration_files()
    assert [path.stem for path in files] == [REQUIRED_SCHEMA_VERSION]
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
