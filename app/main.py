"""
FastAPI application factory and entry point.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.memory.long_term import init_db
from app.observability.telemetry import setup_telemetry

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    # Bootstrap telemetry before anything else
    setup_telemetry()

    app = FastAPI(
        title="AI Agent",
        description=(
            "Production-ready AI Agent with tool calling, "
            "short-term + long-term memory, and safety guardrails."
        ),
        version=settings.service_version,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # ── Request ID middleware ──────────────────────────────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        from app.observability.telemetry import new_request_id
        rid = request.headers.get("X-Request-ID") or new_request_id()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    # ── Global exception handler ───────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    # ── Startup event ──────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup() -> None:
        logger.info("Starting AI Agent (env=%s)", settings.app_env)
        await init_db()

    # ── Routes ─────────────────────────────────────────────────────────────
    app.include_router(router, prefix="/api/v1")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.app_host,
        port=s.app_port,
        reload=s.app_env == "development",
        log_level=s.log_level.lower(),
    )
