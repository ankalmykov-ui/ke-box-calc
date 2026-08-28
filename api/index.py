from fastapi import FastAPI

try:
    from ke_box_calc.main import app
except Exception as startup_exception:  # pragma: no cover - Vercel packaging guard
    diagnostic = {
        "status": "startup_failed",
        "error_type": type(startup_exception).__name__,
        "missing_module": getattr(startup_exception, "name", None),
    }
    app = FastAPI()

    @app.get("/{path:path}", status_code=500)
    def startup_failure(path: str) -> dict:
        return diagnostic


__all__ = ["app"]
