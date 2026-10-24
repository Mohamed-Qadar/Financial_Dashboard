"""Structured (JSON lines) logging with the current request ID.

JSON encoding escapes newlines and other control characters, so user-controlled text in a
log message cannot forge extra log lines.
"""

import json
import logging
from datetime import UTC, datetime

from apps.core.request_id import current_request_id

# Attributes passed with ``extra=`` that are copied into the JSON object.
EXTRA_FIELDS = (
    "method",
    "path",
    "status",
    "duration_ms",
    "audit_event",
    "audit_outcome",
    "audit_request_id",
)


class RequestIDFilter(logging.Filter):
    """Attach the current request ID (or None outside a request) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for field in EXTRA_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)
