from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CompositionLayerInput(BaseModel):
    layer_no: int = Field(gt=0)
    layer_role: str = Field(min_length=1, max_length=120)
    material_id: UUID
    corrugation_coefficient: Decimal = Field(default=Decimal("1"), gt=0)


class CompositionVersionInput(BaseModel):
    board_grade_code: str = Field(min_length=1, max_length=120)
    profile_code: str = Field(min_length=1, max_length=40)
    status: Literal["draft", "approved"] = "draft"
    change_reason: str | None = Field(default=None, max_length=1000)
    created_by: str = Field(min_length=1, max_length=240)
    approved_by: str | None = Field(default=None, max_length=240)
    layers: list[CompositionLayerInput]

    @model_validator(mode="after")
    def validate_layers_and_approval(self):
        if len(self.layers) not in {3, 5}:
            raise ValueError("Композиция должна содержать 3 или 5 слоёв")
        numbers = sorted(layer.layer_no for layer in self.layers)
        if numbers != list(range(1, len(self.layers) + 1)):
            raise ValueError("Номера слоёв должны идти подряд, начиная с 1")
        if self.status == "approved" and not self.approved_by:
            raise ValueError("Для утверждённой версии требуется approved_by")
        return self


class CompositionCreate(CompositionVersionInput):
    organization_id: UUID
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=500)


class BctResultCreate(BaseModel):
    result_kind: Literal["calculated", "actual"]
    bct_kn: Decimal = Field(gt=0)
    original_value: Decimal | None = Field(default=None, gt=0)
    original_unit: str | None = Field(default=None, max_length=40)
    method_code: str | None = Field(default=None, max_length=120)
    method_version: str | None = Field(default=None, max_length=120)
    sample_count: int | None = Field(default=None, gt=0)
    measured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_system: str = Field(min_length=1, max_length=120)
    source_reference: str | None = Field(default=None, max_length=500)
    lab_protocol: str | None = Field(default=None, max_length=500)
    recorded_by: str = Field(min_length=1, max_length=240)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def calculated_result_requires_versioned_method(self):
        if self.result_kind == "calculated" and (
            not self.method_code or not self.method_version
        ):
            raise ValueError(
                "Для расчётного BCT требуются method_code и method_version"
            )
        return self


class CostSnapshotCreate(BaseModel):
    total_cost_rub_m2: Decimal = Field(ge=0)
    material_cost_rub_m2: Decimal | None = Field(default=None, ge=0)
    conversion_cost_rub_m2: Decimal | None = Field(default=None, ge=0)
    price_effective_at: datetime
    calculation_method: str = Field(min_length=1, max_length=240)
    source_system: str = Field(default="ke-box-calc", min_length=1, max_length=120)
    recorded_by: str = Field(min_length=1, max_length=240)
    breakdown: dict[str, Any] = Field(default_factory=dict)
