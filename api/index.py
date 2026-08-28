from fastapi import FastAPI

from ke_box_calc import APP_VERSION
from ke_box_calc.application import configure_app

app = FastAPI(
    title="KE | BOX CALC API",
    version=APP_VERSION,
    docs_url="/api/v2/docs",
    openapi_url="/api/v2/openapi.json",
)
configure_app(app)


__all__ = ["app"]
