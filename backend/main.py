"""OilTrace Main FastAPI Application.

Authoritative backend service for AI-Driven Oil Spill Detection and Responsible Vessel Attribution.
Exposes REST and GIS GeoJSON endpoints for the React frontend, orchestrates scientific domain
pipelines, integrates PostgreSQL/PostGIS and Celery background workers, and supports demo fallback mode.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sys
from typing import Any, Dict

# Ensure project root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.router import api_router
from backend.core.config import settings
from backend.core.exceptions import OilTraceException
from backend.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown event handler."""
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode (DEMO_MODE={settings.DEMO_MODE})")
    logger.info(f"Allowed CORS origins: {settings.CORS_ORIGINS}")
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title="OilTrace Attribution API",
    description="FastAPI interface for OilTrace Satellite Detection & Responsible Vessel Attribution System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS with strict environment-specified origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(OilTraceException)
async def oiltrace_exception_handler(request: Request, exc: OilTraceException):
    """Handle known domain exceptions without exposing internal traces."""
    logger.warning(f"Domain exception on {request.method} {request.url.path}: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic request validation errors."""
    logger.warning(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "FAILED",
            "error_code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions to prevent stack trace leaks to client."""
    logger.error(f"Unhandled internal server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "FAILED",
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected internal error occurred. Please consult server logs.",
        },
    )


# Mount Master API Router
app.include_router(api_router)


# Standalone runner
if __name__ == "__main__":
    import uvicorn
    print("Starting OilTrace FastAPI backend on http://127.0.0.1:8000 ...")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
