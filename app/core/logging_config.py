"""
Logging Configuration Module
Configures Python's built-in logging with structured JSON output for production
and human-readable coloured output for development.
"""

import logging
import logging.config
import sys
import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


# ──────────────────────────────────────────────
# Custom JSON Formatter
# ──────────────────────────────────────────────


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for production / log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Merge any extra keys passed via `logger.info("msg", extra={...})`
        for key in ("user_id", "email", "project_id", "token_id", "ip", "method", "path", "status_code", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, default=str)


# ──────────────────────────────────────────────
# Coloured console formatter (dev)
# ──────────────────────────────────────────────


class ColouredFormatter(logging.Formatter):
    """Pretty, coloured logs for local development."""

    COLOURS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, self.RESET)
        ts = datetime.now().strftime("%H:%M:%S")
        base = f"{colour}{ts} [{record.levelname:<8}]{self.RESET} {record.name}: {record.getMessage()}"
        if record.exc_info and record.exc_info[1]:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ──────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────


def setup_logging() -> None:
    """
    Configure root logger and library loggers.
    Call this once at application startup (in lifespan).
    """

    is_debug = settings.DEBUG
    level = logging.DEBUG if is_debug else logging.INFO

    # Choose formatter
    if is_debug:
        formatter = ColouredFormatter()
    else:
        formatter = JSONFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    # Remove any default handlers
    root.handlers.clear()
    root.addHandler(console_handler)

    # Quieten noisy third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger under the ``logiscout`` namespace.

    Usage::

        from app.core.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("User signed in", extra={"user_id": "abc123"})
    """
    return logging.getLogger(f"logiscout.{name}")
