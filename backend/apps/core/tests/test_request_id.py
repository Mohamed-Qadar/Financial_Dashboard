import json
import uuid
from unittest import mock

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import path
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.core.middleware import RequestIDMiddleware
from apps.core.request_id import current_request_id, resolve_request_id
from apps.core.views import not_found, server_error

VALID_ID = "3f2b8c1e-4d5a-4b6c-9e7f-0a1b2c3d4e5f"


class EchoRequestIDView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        return Response({"seen": current_request_id()})


class AmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class ValidatingView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        AmountSerializer(data=request.data).is_valid(raise_exception=True)
        return Response(status=204)


class ProtectedView(APIView):
    def get(self, request):
        return Response({})


urlpatterns = [
    path("echo/", EchoRequestIDView.as_view()),
    path("validate/", ValidatingView.as_view()),
    path("protected/", ProtectedView.as_view()),
]
handler404 = "apps.core.views.not_found"

pytestmark = pytest.mark.urls(__name__)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _is_uuid4(value: str) -> bool:
    try:
        return uuid.UUID(value).version == 4 and str(uuid.UUID(value)) == value
    except ValueError:
        return False


# --- validation policy ------------------------------------------------------------------


def test_valid_uuid_is_accepted_and_lowercased():
    assert resolve_request_id(VALID_ID.upper()) == VALID_ID


@pytest.mark.parametrize(
    "supplied",
    [
        None,
        "",
        "abc",
        "not-a-uuid-at-all-but-36-characters",
        "{" + VALID_ID + "}",
        "urn:uuid:" + VALID_ID,
        VALID_ID.replace("-", ""),
        VALID_ID + "\r\nX-Injected: 1",
        VALID_ID + '\n{"level": "CRITICAL"}',
        VALID_ID + " ",
        "a" * 10_000,
        VALID_ID[:-1] + "g",
    ],
)
def test_invalid_or_missing_ids_are_replaced(supplied):
    resolved = resolve_request_id(supplied)

    assert _is_uuid4(resolved)
    assert resolved != supplied


# --- propagation ------------------------------------------------------------------------


def test_generated_id_is_returned_in_header_and_visible_to_the_view(client):
    response = client.get("/echo/")

    request_id = response["X-Request-ID"]
    assert _is_uuid4(request_id)
    assert response.json() == {"seen": request_id}


def test_valid_incoming_id_is_propagated(client):
    response = client.get("/echo/", HTTP_X_REQUEST_ID=VALID_ID.upper())

    assert response["X-Request-ID"] == VALID_ID
    assert response.json() == {"seen": VALID_ID}


def test_injection_attempt_is_not_echoed(client):
    response = client.get("/echo/", HTTP_X_REQUEST_ID=VALID_ID + "\nINJECTED")

    assert response["X-Request-ID"] != VALID_ID
    assert "INJECTED" not in response["X-Request-ID"]
    assert _is_uuid4(response["X-Request-ID"])


def test_each_request_gets_its_own_id(client):
    ids = {client.get("/echo/")["X-Request-ID"] for _ in range(5)}

    assert len(ids) == 5


def test_id_is_unbound_after_the_request(client):
    client.get("/echo/")

    assert current_request_id() is None


def test_id_is_unbound_even_when_the_view_raises():
    middleware = RequestIDMiddleware(mock.Mock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        middleware(RequestFactory().get("/"))

    assert current_request_id() is None


def test_access_log_line_has_request_id_and_no_query_string(client, caplog):
    caplog.set_level("INFO", logger="apps.core.request")

    response = client.get("/echo/?email=secret@example.com", HTTP_X_REQUEST_ID=VALID_ID)

    [record] = [r for r in caplog.records if r.name == "apps.core.request"]
    assert record.path == "/echo/"
    assert record.status == 200
    assert record.method == "GET"
    assert response["X-Request-ID"] == VALID_ID
    assert "secret@example.com" not in record.getMessage()


# --- error responses --------------------------------------------------------------------


def test_validation_error_carries_request_id(client):
    response = client.post("/validate/", {"amount": "x"}, format="json", HTTP_X_REQUEST_ID=VALID_ID)

    assert response.status_code == 400
    assert response.json()["error"]["request_id"] == VALID_ID


def test_authentication_error_carries_request_id(client):
    response = client.get("/protected/")

    assert response.json()["error"]["request_id"] == response["X-Request-ID"]


def test_django_404_carries_request_id(client):
    response = client.get("/missing/", HTTP_X_REQUEST_ID=VALID_ID)

    assert response.status_code == 404
    assert response.json()["error"]["request_id"] == VALID_ID


def test_django_500_handler_carries_request_id():
    request = RequestFactory().get("/", HTTP_X_REQUEST_ID=VALID_ID)
    middleware = RequestIDMiddleware(lambda req: server_error(req))

    response = middleware(request)

    assert response.status_code == 500
    assert response["X-Request-ID"] == VALID_ID
    assert json.loads(response.content)["error"]["request_id"] == VALID_ID


def test_error_outside_a_request_has_no_request_id():
    response = not_found(RequestFactory().get("/"), Exception())

    assert "request_id" not in json.loads(response.content)["error"]


def test_middleware_sets_header_on_plain_django_responses():
    middleware = RequestIDMiddleware(lambda req: HttpResponse("ok"))

    response = middleware(RequestFactory().get("/"))

    assert _is_uuid4(response["X-Request-ID"])
