from unittest import mock

import pytest
from django.db import OperationalError
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_liveness_returns_ok_without_authentication_or_database(client):
    # No django_db mark: pytest-django raises if the view touches the database.
    response = client.get(reverse("health-live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_reports_database_ok(client):
    response = client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_readiness_returns_503_when_database_is_unavailable(client):
    with mock.patch(
        "apps.core.views.connection.cursor",
        side_effect=OperationalError("connection refused to 10.0.0.5"),
    ):
        response = client.get(reverse("health-ready"))

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "unavailable"}}
    # Infrastructure details stay in the logs.
    assert "10.0.0.5" not in response.content.decode()
