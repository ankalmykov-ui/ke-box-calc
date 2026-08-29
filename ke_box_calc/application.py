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


def configure_app(app: FastAPI) -> None:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(api_v2_router)
    app.add_api_route("/", index, include_in_schema=False)
    app.add_api_route("/health", legacy_health_alias, include_in_schema=False)
    app.mount("/", StaticFiles(directory=PUBLIC, check_dir=False), name="public")


def index() -> FileResponse:
    return FileResponse(PUBLIC / "index.html")


def legacy_health_alias() -> dict:
    return {"status": "ok", "app_version": APP_VERSION, "api": "/api/v2"}
