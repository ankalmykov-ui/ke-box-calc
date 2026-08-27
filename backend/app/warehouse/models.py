from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class OrganizationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)


class SiteCreate(BaseModel):
    organization_id: UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)


class WarehouseCreate(BaseModel):
    site_id: UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)


class ExternalIdentifierInput(BaseModel):
    source_system: str = Field(min_length=1, max_length=80)
    external_code: str = Field(min_length=1, max_length=240)
    external_variant: str | None = Field(default=None, max_length=240)


class MaterialWidthInput(BaseModel):
    width_mm: Decimal = Field(gt=0)
    status: Literal["active", "inactive", "requires_verification"] = "active"
    valid_from: date = Field(default_factory=date.today)
    source_name: str | None = None


class MaterialCreate(BaseModel):
    organization_id: UUID
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=500)
    technological_designation: str | None = None
    material_type: str = Field(min_length=1, max_length=120)
    gsm: Decimal = Field(gt=0)
    color: str | None = None
    surface_type: str | None = None
    manufacturer: str | None = None
    supplier: str | None = None
    procurement_status: Literal[
        "purchased",
        "temporarily_not_purchased",
        "stock_only",
        "unavailable",
        "requires_classification",
    ] = "requires_classification"
    classification_status: Literal["approved", "requires_classification", "rejected"] = (
        "requires_classification"
    )
    source_name: str | None = None
    valid_from: date = Field(default_factory=date.today)
    external_identifiers: list[ExternalIdentifierInput] = Field(default_factory=list)
    widths: list[MaterialWidthInput] = Field(default_factory=list)


class StockQuantityInput(BaseModel):
    quantity: Decimal = Field(gt=0)
    unit_code: str = Field(default="kg", min_length=1, max_length=24)
    base_quantity_kg: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_conversion_for_non_kg(self):
        if self.unit_code.lower() == "kg":
            if self.base_quantity_kg is None:
                self.base_quantity_kg = self.quantity
        elif self.base_quantity_kg is None:
            raise ValueError("Для единицы, отличной от kg, требуется base_quantity_kg")
        return self


class ReceiptLineInput(StockQuantityInput):
    material_id: UUID
    lot_code: str = Field(min_length=1, max_length=240)
    roll_code: str | None = Field(default=None, max_length=240)
    width_mm: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(default="RUB", min_length=3, max_length=3)

    @model_validator(mode="after")
    def roll_requires_width(self):
        if self.roll_code and self.width_mm is None:
            raise ValueError("Для конкретного рулона требуется width_mm")
        return self


class ReceiptCreate(BaseModel):
    warehouse_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=240)
    created_by: str = Field(min_length=1, max_length=240)
    source_system: str = Field(default="manual", min_length=1, max_length=80)
    source_reference: str | None = None
    reason: str | None = None
    lines: list[ReceiptLineInput] = Field(min_length=1)


class WriteoffLineInput(StockQuantityInput):
    material_id: UUID
    lot_id: UUID
    roll_id: UUID | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(default="RUB", min_length=3, max_length=3)


class WriteoffConfirm(BaseModel):
    warehouse_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=240)
    confirmed_by: str = Field(min_length=1, max_length=240)
    order_reference: str | None = None
    layout_variant_reference: str | None = None
    calculation_snapshot_id: UUID | None = None
    reason: str | None = None
    lines: list[WriteoffLineInput] = Field(min_length=1)


class ReversalCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=240)
    reversed_by: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=3, max_length=1000)
