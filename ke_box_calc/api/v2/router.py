from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ke_box_calc import API_VERSION, APP_VERSION
from ke_box_calc.core.config import get_settings
from ke_box_calc.db.connection import ping_database
from ke_box_calc.db.migrator import load_migrations
from ke_box_calc.domains.calculation.references import get_active_references
from ke_box_calc.domains.calculation.service import (
    calculate_first_variant,
    calculate_order_automatically,
)
from ke_box_calc.domains.materials.service import (
    add_material_with_balance,
    get_materials_by_ids,
    import_opening_balance,
    list_materials,
    list_materials_for_calculation,
)

router = APIRouter(prefix="/api/v2")


class MaterialCreate(BaseModel):
    name: str = Field(min_length=3, max_length=300)
    material_type: str = Field(pattern="^(paper|liner)$")
    grammage_g_m2: Decimal = Field(gt=0, le=1000)
    width_mm: int = Field(ge=500, le=3000)
    manufacturer: str | None = Field(default=None, max_length=200)
    quantity_kg: Decimal = Field(gt=0)
    price_rub_kg: Decimal | None = Field(default=None, ge=0)
    source_name: str = Field(default="Ручное добавление", max_length=200)


class OpeningBalanceItem(BaseModel):
    name: str = Field(min_length=3, max_length=300)
    material_type: str = Field(pattern="^(paper|liner)$")
    grammage_g_m2: Decimal = Field(gt=0, le=1000)
    width_mm: int = Field(ge=500, le=3000)
    manufacturer: str | None = Field(default=None, max_length=200)
    quantity_kg: Decimal = Field(gt=0)
    price_rub_kg: Decimal | None = Field(default=None, ge=0)


class OpeningBalanceImport(BaseModel):
    source_name: str = Field(min_length=3, max_length=200)
    source_checksum: str = Field(pattern="^[0-9a-f]{64}$")
    items: list[OpeningBalanceItem] = Field(min_length=1, max_length=1000)


class CalculationRequest(BaseModel):
    length_mm: int = Field(gt=0, le=5000)
    width_mm: int = Field(gt=0, le=5000)
    height_mm: int = Field(gt=0, le=5000)
    quantity: int = Field(gt=0, le=1_000_000)
    material_ids: list[UUID] = Field(min_length=3, max_length=3)
    technological_trim_mm: int = Field(default=0, ge=0, le=50)


class OrderItemRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    length_mm: int = Field(gt=0, le=5000)
    width_mm: int = Field(gt=0, le=5000)
    height_mm: int = Field(gt=0, le=5000)
    quantity: int = Field(gt=0, le=1_000_000)
    board_grade: str = Field(min_length=2, max_length=20)
    required_bct_kn: Decimal | None = Field(default=None, gt=0, le=1000)
    profile: str = Field(pattern="^(E|B|C)$")
    technological_trim_mm: int = Field(default=0, ge=0, le=50)


class AutomaticCalculationRequest(BaseModel):
    items: list[OrderItemRequest] = Field(min_length=1, max_length=8)


@router.get("/meta", tags=["system"])
def meta() -> dict:
    settings = get_settings()
    return {
        "app": "KE | BOX CALC",
        "app_version": APP_VERSION,
        "api_version": API_VERSION,
        "stage": 4,
        "stage_name": "automatic_order_calculation",
        "calculation_engine": "automatic_stock_optimizer",
        "database": {
            "configured": settings.database_configured,
            "required": settings.database_required,
            "schema_min": "2.0.0",
            "schema_max": "2.0.x",
            "known_migrations": [migration.version for migration in load_migrations()],
        },
    }


@router.get("/health/live", tags=["system"])
def live() -> dict:
    return {"status": "ok", "app_version": APP_VERSION}


@router.get("/health/ready", tags=["system"])
def ready() -> dict:
    settings = get_settings()
    if not settings.database_configured:
        if settings.database_required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DATABASE_URL is required but not configured",
            )
        return {"status": "ok", "database": "not_required"}
    if not ping_database():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )
    return {"status": "ok", "database": "ready"}


@router.get("/materials", tags=["materials"])
def materials() -> dict:
    try:
        return {"items": list_materials()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="База сырья пока недоступна") from exc


@router.post("/materials", status_code=201, tags=["materials"])
def create_material(payload: MaterialCreate) -> dict:
    try:
        return add_material_with_balance(**payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/materials/import-opening-balance", status_code=201, tags=["materials"])
def create_opening_balance(payload: OpeningBalanceImport) -> dict:
    try:
        values = payload.model_dump()
        values["items"] = [item.model_dump() for item in payload.items]
        return import_opening_balance(**values)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/calculations/first-variant", tags=["calculation"])
def first_variant(payload: CalculationRequest) -> dict:
    try:
        values = payload.model_dump()
        material_ids = values.pop("material_ids")
        material_rows = get_materials_by_ids(material_ids)
        rows_by_id = {row["id"]: row for row in material_rows}
        ordered_rows = [
            rows_by_id[material_id] for material_id in material_ids if material_id in rows_by_id
        ]
        return calculate_first_variant(materials=ordered_rows, **values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="База сырья пока недоступна") from exc


@router.post("/calculations/auto", tags=["calculation"])
def automatic_calculation(payload: AutomaticCalculationRequest) -> dict:
    try:
        return calculate_order_automatically(
            items=[item.model_dump() for item in payload.items],
            materials=list_materials_for_calculation(),
            references=get_active_references(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Автоматический расчёт временно недоступен"
        ) from exc
