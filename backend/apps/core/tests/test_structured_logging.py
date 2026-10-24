import json
import logging
import sys

from apps.core.request_id import bind_request_id, unbind_request_id
from apps.core.structured_logging import JSONFormatter, RequestIDFilter

REQUEST_ID = "3f2b8c1e-4d5a-4b6c-9e7f-0a1b2c3d4e5f"


def _record(message="hello", **extra):
    record = logging.LogRecord("test.logger", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _format(record):
    RequestIDFilter().filter(record)
    return JSONFormatter().format(record)


def test_log_line_is_single_json_object_with_request_id():
    token = bind_request_id(REQUEST_ID)
    try:
        line = _format(_record("payment recorded"))
    finally:
        unbind_request_id(token)

    entry = json.loads(line)
    assert entry["message"] == "payment recorded"
    assert entry["request_id"] == REQUEST_ID
    assert entry["level"] == "INFO"
    assert entry["logger"] == "test.logger"
    assert entry["timestamp"].endswith("+00:00")


def test_request_id_is_null_outside_a_request():
    assert json.loads(_format(_record()))["request_id"] is None


def test_user_controlled_newlines_cannot_forge_log_lines():
    forged = 'name\n{"level": "CRITICAL", "message": "admin logged in"}\r\n\x1b[31m'

    line = _format(_record(f"login for {forged}"))

    assert "\n" not in line and "\r" not in line and "\x1b" not in line
    assert json.loads(line)["message"] == f"login for {forged}"


def test_extra_request_fields_are_included():
    entry = json.loads(_format(_record(method="GET", path="/x/", status=200, duration_ms=1.5)))

    assert (entry["method"], entry["path"], entry["status"], entry["duration_ms"]) == (
        "GET",
        "/x/",
        200,
        1.5,
    )


def test_exceptions_are_kept_inside_the_json_object():
    try:
        raise ValueError("bad\nthing")
    except ValueError:
        record = _record("failed")
        record.exc_info = sys.exc_info()

    line = _format(record)

    assert "\n" not in line
    assert "ValueError" in json.loads(line)["exception"]
