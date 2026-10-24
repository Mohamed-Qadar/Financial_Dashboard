"""Uniform error responses for the API.

Every error has the shape {"error": {"code": str, "message": str, "details"?: object}}.
"""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.utils.translation import gettext as _
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        # Not an API exception: let Django log it and answer through handler500.
        return None

    if isinstance(exc, exceptions.ValidationError):
        response.data = error_payload("validation_error", _("Invalid input."), response.data)
    elif isinstance(exc, exceptions.APIException):
        detail = exc.detail
        code = getattr(detail, "code", None) or exc.default_code
        response.data = error_payload(str(code), str(detail))
    return response
