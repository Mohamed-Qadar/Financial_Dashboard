"""Request IDs: one identifier per HTTP request, shared by logs, error responses and audit events.

Validation policy for a client-supplied ``X-Request-ID``:
- accepted only as a canonical hyphenated UUID (8-4-4-4-12 hex digits, 36 characters);
- normalized to lower case;
- anything else (missing, empty, longer, other formats, control characters) is ignored and a
  new random UUID4 is generated.

Request IDs are for correlation only. A client can choose any valid UUID, so they are never
used for security decisions.
"""

import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 36
_UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

_current_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def resolve_request_id(supplied: str | None) -> str:
    """Return the supplied ID if it passes the validation policy, otherwise a new one."""
    if supplied and len(supplied) <= MAX_REQUEST_ID_LENGTH and _UUID_PATTERN.fullmatch(supplied):
        return supplied.lower()
    return str(uuid.uuid4())


def current_request_id() -> str | None:
    """The ID of the request being handled by this thread/task, if any."""
    return _current_request_id.get()


def bind_request_id(request_id: str):
    """Set the current request ID; returns a token for ``unbind_request_id``."""
    return _current_request_id.set(request_id)


def unbind_request_id(token) -> None:
    _current_request_id.reset(token)
