"""
Structured logging configuration.

Provides JSON-formatted logs for production and human-readable logs for development.
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)
        # Merge extra fields added via logger.info("msg", extra={...})
        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "max_workers",
            "service",
            "detail",
        ):
            value = getattr(record, key, None)
            if value is not None:
                log_data[key] = value
        return json.dumps(log_data, default=str)


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """
    Configure root logger.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True use JSON output; if False use human-readable format.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers to avoid duplicates
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s")
        )

    root.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
