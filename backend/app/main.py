from contextlib import asynccontextmanager
from pathlib import Path
import json

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .calc.corrugator import CorrugatorConfig, load_corrugator_reference
from .calc.fefco0201 import calculate_fefco0201_profile, load_profile_rules
from .calc.full import full_calculation, prepare_order_item, validate_prepared_item
from .calc.grade import load_grade_norms
from .calc.machines import load_equipment_reference
from .calc.optimizer import CandidateLayer, CompositionCandidate, Material
from .compositions.router import router as compositions_router
from .db import database_url, schema_status
from .db_migrations import apply_migrations, should_apply_migrations_on_startup
from .importers.lab import parse_lab_import
from .importers.materials_1c import ImportFormatError, parse_material_import
from .importers.orders import parse_order_import, validate_order_rows
from .warehouse.router import router as warehouse_router

APP_VERSION = "0.9.0-dev"
API_VERSION = "v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if should_apply_migrations_on_startup():
        apply_migrations()
    yield


app = FastAPI(title="KE | BOX CALC", version=APP_VERSION, lifespan=lifespan)
STATIC = Path(__file__).parent / "static"
DATA = Path(__file__).parent / "data"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.include_router(warehouse_router)
app.include_router(compositions_router)


class FefcoProfileRequest(BaseModel):
    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    profile: str
    manufacturer_joint_override_mm: float | None = Field(default=None, gt=0)
    caliper_override_mm: float | None = Field(default=None, gt=0)


class MaterialRequest(BaseModel):
    code_1c: str
    variant_1c: str | None = None
    name: str
    gsm: float = Field(gt=0)
    price_rub_t: float = Field(gt=0)
    stock_kg: float | None = Field(default=None, ge=0)
    procurement_status: str = "active"
    supplier: str | None = None
    manufacturer: str | None = None
    material_type: str | None = None
    roll_width_mm: float | None = Field(default=None, gt=0)
    price_date: str | None = None
    stock_date: str | None = None
    technological_code: str | None = None
    color: str | None = None


class CandidateLayerRequest(BaseModel):
    role: str
    material_key: str
    corrugation_coefficient: float = Field(default=1.0, gt=0)


class CandidateRequest(BaseModel):
    code: str
    board_grade: str
    profile: str
    layers: list[CandidateLayerRequest]
    status: str = "approved"
    evidence: str = "technologist_approved"
    strength_reserve_pct: float | None = None
    lab_pass_count: int = 0


class OrderItemRequest(BaseModel):
    code: str
    product_type: str = "0201"
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    blank_length_mm: float | None = None
    blank_width_mm: float | None = None
    quantity: int = Field(gt=0)
    required_board_grade: str
    profile: str
    colors: int = Field(default=1, ge=0)
    die_cut: bool = False
    manufacturer_joint_mm: float | None = None
    caliper_mm: float | None = None
    client: str | None = None
    order_ref: str | None = None
    due_date: str | None = None


class FullCalculationRequest(BaseModel):
    items: list[OrderItemRequest]
    roll_widths_mm: list[float] = Field(default_factory=list)
    materials: list[MaterialRequest] = Field(default_factory=list)
    candidates: list[CandidateRequest] = Field(default_factory=list)
    machine_hourly_costs: dict[str, float] = Field(default_factory=dict)
    other_waste_pct: float = Field(default=0, ge=0, lt=100)
    working_width_mm: float = Field(default=2100, gt=0)
    max_streams: int = Field(default=5, gt=0)
    planning_horizon_days: int = Field(default=1, ge=1, le=3)


class ItemValidationRequest(BaseModel):
    item: OrderItemRequest
    working_width_mm: float = Field(default=2100, gt=0)


class ValidateRowsRequest(BaseModel):
    rows: list[dict]


@app.get("/")
def root():
    return FileResponse(STATIC / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def sw():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "KE | BOX CALC",
        "version": APP_VERSION,
        "database": "configured" if database_url() else "not_configured",
    }


@app.get("/api/v1/meta")
def api_meta():
    return {
        "app": "KE | BOX CALC",
        "app_version": APP_VERSION,
        "api_version": API_VERSION,
        "spec": "KE | BOX CALC — техническое задание v2.2",
        "schema": schema_status(),
    }


@app.get("/api/modules")
def modules():
    return {
        "version": APP_VERSION,
        "spec": "KE | BOX CALC — техническое задание v2.2",
        "scope_v1": ["SHEET", "FEFCO 0201"],
        "modules": [
            {"code": "geometry", "name": "Геометрия FEFCO 0201", "status": "working"},
            {"code": "orders", "name": "Ручной ввод + импорт изделий", "status": "working"},
            {"code": "materials", "name": "Сырьё и складской учёт", "status": "v0.9_foundation"},
            {"code": "inventory", "name": "Поступления и инвентаризация", "status": "api_foundation"},
            {"code": "writeoff", "name": "Отдельное подтверждение списания", "status": "api_foundation"},
            {"code": "compositions", "name": "Версии композиций, BCT и стоимость/м²", "status": "api_foundation"},
            {"code": "lab", "name": "Импорт лаборатории", "status": "preview"},
            {"code": "corrugator", "name": "Оптимизатор раскроя + альтернативы", "status": "working"},
            {"code": "bct", "name": "Расчётный BCT McKee", "status": "working_estimate"},
            {"code": "machines", "name": "P660 / 2Print / SRPACK", "status": "working_reference"},
            {"code": "reports", "name": "PDF-отчёты", "status": "ui_scaffold"},
            {"code": "snapshots", "name": "Snapshots/PostgreSQL", "status": "migration_foundation"},
            {"code": "full", "name": "Сквозной расчёт заказа", "status": "working_partial_cost"},
        ],
    }


@app.get("/api/reference/board-grade-norms")
def board_grade_norms():
    return load_grade_norms()


@app.get("/api/reference/equipment")
@app.get("/api/reference/equipment-v06")
def equipment():
    return load_equipment_reference()


@app.get("/api/reference/corrugator")
@app.get("/api/reference/corrugator-v06")
def corrugator():
    return load_corrugator_reference()


@app.get("/api/reference/fefco0201-profile-rules")
def fefco_rules():
    return load_profile_rules()


@app.get("/api/reference/composition-catalog")
def composition_catalog():
    return json.loads((DATA / "composition_catalog_example.json").read_text(encoding="utf-8"))


@app.get("/api/reference/1c-import-format")
def one_c_format():
    return json.loads((DATA / "one_c_import_format.json").read_text(encoding="utf-8"))


@app.get("/api/reference/order-template")
def order_template():
    return FileResponse(STATIC / "KE_BOX_CALC_Шаблон_изделий_v0.7.xlsx")


@app.post("/api/calc/fefco0201/profile")
def calc_fefco(req: FefcoProfileRequest):
    try:
        return calculate_fefco0201_profile(
            req.length_mm,
            req.width_mm,
            req.height_mm,
            req.profile,
            manufacturer_joint_override_mm=req.manufacturer_joint_override_mm,
            caliper_override_mm=req.caliper_override_mm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/validate/item")
def validate_item(req: ItemValidationRequest):
    try:
        prepared = prepare_order_item(req.item.model_dump())
        return validate_prepared_item(prepared, req.working_width_mm)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/orders/preview")
async def preview_orders(file: UploadFile = File(...)):
    try:
        return parse_order_import(await file.read(), file.filename or "items.xlsx")
    except ImportFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/orders/validate")
def validate_orders(req: ValidateRowsRequest):
    return validate_order_rows(req.rows)


@app.post("/api/import/1c/materials/preview", deprecated=True)
@app.post("/api/v1/inventory/imports/1c/preview")
async def preview_1c(file: UploadFile = File(...)):
    try:
        return parse_material_import(await file.read(), file.filename or "materials.xlsx")
    except ImportFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/lab/preview")
async def preview_lab(file: UploadFile = File(...)):
    try:
        return parse_lab_import(await file.read(), file.filename or "lab.xlsx")
    except ImportFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/calc/full")
def calc_full(req: FullCalculationRequest):
    try:
        materials = [Material(**x.model_dump()) for x in req.materials]
        candidates = [
            CompositionCandidate(
                code=c.code,
                board_grade=c.board_grade,
                profile=c.profile,
                layers=tuple(CandidateLayer(**x.model_dump()) for x in c.layers),
                status=c.status,
                evidence=c.evidence,
                strength_reserve_pct=c.strength_reserve_pct,
                lab_pass_count=c.lab_pass_count,
            )
            for c in req.candidates
        ]
        roll_widths = [float(x) for x in req.roll_widths_mm if float(x) > 0]
        roll_width_source = "manual"
        if not roll_widths:
            roll_widths = sorted(
                {float(m.roll_width_mm) for m in materials if m.roll_width_mm and m.procurement_status != "unavailable"},
                reverse=True,
            )
            roll_width_source = "request_materials"
        if not roll_widths:
            raise ValueError(
                "Не заданы доступные ширины рулонов: введите их вручную или выберите сырьё из склада."
            )

        result = full_calculation(
            [x.model_dump() for x in req.items],
            roll_widths,
            materials,
            candidates,
            req.machine_hourly_costs,
            CorrugatorConfig(req.working_width_mm, req.max_streams, 2),
            req.other_waste_pct,
        )
        result["planning_horizon_days"] = req.planning_horizon_days
        result["roll_width_source"] = roll_width_source
        return result
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
