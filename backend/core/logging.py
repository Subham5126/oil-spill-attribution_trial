"""OilTrace Structured Logging Module.

Provides standard logging with execution duration, investigation context, and stage tracking.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Dict, Optional


def get_logger(name: str = "oiltrace") -> logging.Logger:
    """Return a configured logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = get_logger("oiltrace.backend")


class PipelineStageLogger:
    """Context manager for measuring and logging pipeline stage execution."""

    def __init__(self, stage_name: str, investigation_id: Optional[str] = None):
        self.stage_name = stage_name
        self.investigation_id = investigation_id or "N/A"
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        logger.info(
            f"[STAGE_START] investigation={self.investigation_id} stage='{self.stage_name}'"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if exc_type is not None:
            logger.error(
                f"[STAGE_FAIL] investigation={self.investigation_id} stage='{self.stage_name}' "
                f"duration={duration:.2f}s error='{exc_val}'"
            )
        else:
            logger.info(
                f"[STAGE_PASS] investigation={self.investigation_id} stage='{self.stage_name}' "
                f"duration={duration:.2f}s"
            )
        return False
