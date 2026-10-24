import logging
import time

from apps.core.request_id import (
    REQUEST_ID_HEADER,
    bind_request_id,
    resolve_request_id,
    unbind_request_id,
)

access_logger = logging.getLogger("apps.core.request")

MAX_LOGGED_PATH_LENGTH = 200


class RequestIDMiddleware:
    """Assign a request ID, expose it to logs and responses, and log one line per request.

    Must be the first middleware so every response (including ones produced by other
    middleware) carries the header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.request_id = request_id
        token = bind_request_id(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            access_logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    # Path only: query strings may carry personal data.
                    "path": request.path[:MAX_LOGGED_PATH_LENGTH],
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                },
            )
            return response
        finally:
            unbind_request_id(token)
