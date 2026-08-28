from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ke_box_calc import APP_VERSION
from ke_box_calc.api.v2.router import router as api_v2_router
from ke_box_calc.core.config import get_settings
from ke_box_calc.core.logging import configure_logging

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

settings = get_settings()
configure_logging(settings.app_log_level)

app = FastAPI(
    title="KE | BOX CALC API",
    version=APP_VERSION,
    docs_url="/api/v2/docs",
    openapi_url="/api/v2/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)
app.include_router(api_v2_router)
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(PUBLIC / "index.html")


@app.get("/health", include_in_schema=False)
def legacy_health_alias() -> dict:
    return {"status": "ok", "app_version": APP_VERSION, "api": "/api/v2"}


app.mount("/", StaticFiles(directory=PUBLIC, check_dir=False), name="public")
