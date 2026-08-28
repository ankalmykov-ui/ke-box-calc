import json

try:
    from ke_box_calc.main import app
except Exception as startup_exception:  # pragma: no cover - Vercel packaging guard
    diagnostic = {
        "status": "startup_failed",
        "error_type": type(startup_exception).__name__,
        "missing_module": getattr(startup_exception, "name", None),
    }

    async def app(scope: dict, receive: object, send: object) -> None:
        if scope["type"] != "http":
            return
        body = json.dumps(diagnostic).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


__all__ = ["app"]
