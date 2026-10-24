import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_payload

logger = logging.getLogger(__name__)

HealthResponse = inline_serializer(
    name="HealthResponse",
    fields={
        "status": serializers.ChoiceField(choices=["ok", "unavailable"]),
        "checks": serializers.DictField(child=serializers.CharField(), required=False),
    },
)


class LivenessView(APIView):
    """The process is up and serving requests. Does not touch the database."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: HealthResponse}, tags=["health"])
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    """The service can do useful work: its dependencies (the database) respond."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: HealthResponse, 503: HealthResponse}, tags=["health"])
    def get(self, request: Request) -> Response:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            # Details go to the log only; the response must not reveal infrastructure.
            logger.exception("Readiness check failed: database unavailable")
            return Response(
                {"status": "unavailable", "checks": {"database": "unavailable"}}, status=503
            )
        return Response({"status": "ok", "checks": {"database": "ok"}})


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(error_payload("not_found", _("Not found.")), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        error_payload("server_error", _("An unexpected error occurred.")), status=500
    )
