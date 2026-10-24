import pytest
from django.urls import path
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)


class ValidatingView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        QuantitySerializer(data=request.data).is_valid(raise_exception=True)
        return Response(status=204)


class MissingObjectView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        raise NotFound()


class ProtectedView(APIView):
    """Uses the project default permission classes."""

    def get(self, request):
        return Response({"secret": True})


urlpatterns = [
    path("test/validate/", ValidatingView.as_view()),
    path("test/missing/", MissingObjectView.as_view()),
    path("test/protected/", ProtectedView.as_view()),
]

pytestmark = pytest.mark.urls(__name__)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_validation_errors_use_error_envelope(client):
    response = client.post("/test/validate/", {"quantity": "-1"}, format="json")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Invalid input."
    assert "quantity" in error["details"]


def test_api_exceptions_use_error_envelope(client):
    response = client.get("/test/missing/")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not found."}}


def test_endpoints_require_authentication_by_default(client):
    response = client.get("/test/protected/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"


def test_malformed_json_returns_parse_error(client):
    response = client.post("/test/validate/", data="{not json", content_type="application/json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parse_error"
