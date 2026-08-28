from fastapi import APIRouter, HTTPException, status

from ke_box_calc import API_VERSION, APP_VERSION
from ke_box_calc.core.config import get_settings
from ke_box_calc.db.connection import ping_database
from ke_box_calc.db.migrator import load_migrations

router = APIRouter(prefix="/api/v2")


@router.get("/meta", tags=["system"])
def meta() -> dict:
    settings = get_settings()
    return {
        "app": "KE | BOX CALC",
        "app_version": APP_VERSION,
        "api_version": API_VERSION,
        "stage": 2,
        "stage_name": "technical_foundation",
        "calculation_engine": "not_implemented",
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

