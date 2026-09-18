"""OilTrace Backend Configuration Module.

Centralized configuration loaded from environment variables and .env file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Optional
from dotenv import load_dotenv

# Base repository root directory
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env file if present
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(str(ENV_FILE))
else:
    load_dotenv()


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


def _get_list(key: str, default: List[str]) -> List[str]:
    val = os.getenv(key)
    if not val:
        return default
    # support comma separated or JSON string
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        try:
            return json.loads(val)
        except Exception:
            pass
    return [item.strip() for item in val.split(",") if item.strip()]


class Settings:
    """Application settings with environment variable fallbacks."""

    REPO_ROOT: Path = REPO_ROOT
    APP_NAME: str = os.getenv("APP_NAME", "OilTrace Attribution Backend")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = _get_bool("DEBUG", True)
    API_V1_PREFIX: str = "/api"

    # Operational Mode: DEMO_MODE defaults to False for live data-driven pipeline
    DEMO_MODE: bool = _get_bool("DEMO_MODE", False)

    # Database: defaults to persistent local SQLite database if PostgreSQL is not specified
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{REPO_ROOT / 'data' / 'oiltrace.db'}")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_ECHO: bool = _get_bool("DB_ECHO", False)

    # Redis & Celery
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    CELERY_TASK_ALWAYS_EAGER: bool = _get_bool("CELERY_TASK_ALWAYS_EAGER", False)

    # Directories
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(REPO_ROOT / "data")))
    AIS_DATA_DIR: Path = Path(os.getenv("AIS_DATA_DIR", str(REPO_ROOT / "data" / "ais")))
    OCEAN_DATA_DIR: Path = Path(os.getenv("OCEAN_DATA_DIR", str(REPO_ROOT / "data" / "sample")))
    SATELLITE_DATA_DIR: Path = Path(os.getenv("SATELLITE_DATA_DIR", str(REPO_ROOT / "data" / "satellite")))
    DEMO_OUTPUT_DIR: Path = Path(os.getenv("DEMO_OUTPUT_DIR", str(REPO_ROOT / "demo" / "output")))
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(REPO_ROOT / "data" / "uploads" / "sentinel1")))
    MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(1024 * 1024 * 1024)))  # 1 GiB limit

    # CORS
    CORS_ORIGINS: List[str] = _get_list(
        "CORS_ORIGINS",
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "oiltrace-development-insecure-secret-key-2026")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    COOKIE_SECURE: bool = _get_bool("COOKIE_SECURE", False)  # Set True in production (HTTPS)
    COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "lax")
    MAX_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

    # Global Fishing Watch (GFW) API Configuration
    GFW_API_TOKEN: Optional[str] = os.getenv("GFW_API_TOKEN")

    # AI / Model Configuration
    OILTRACE_MODEL_PROVIDER: str = os.getenv("OILTRACE_MODEL_PROVIDER", "current")
    OILTRACE_MODEL_PATH: Path = Path(os.getenv("OILTRACE_MODEL_PATH", str(REPO_ROOT / "unet_best.pth")))
    M1_MODEL_PATH: Path = Path(os.getenv("M1_MODEL_PATH", str(REPO_ROOT / "ai" / "training" / "checkpoints" / "best_model.pth")))


settings = Settings()
