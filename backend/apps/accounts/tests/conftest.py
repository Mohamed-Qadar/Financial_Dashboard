import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog

PASSWORD = "Correct-Horse-Battery-42"
NEW_PASSWORD = "Another-Strong-Phrase-77"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        "hodan@example.com", password=PASSWORD, full_name="Hodan Ali"
    )


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def login(client: APIClient, email: str, password: str, **extra):
    return client.post(
        reverse("auth-login"), {"email": email, "password": password}, format="json", **extra
    )


def logged_in_client(email: str = "hodan@example.com", password: str = PASSWORD) -> APIClient:
    client = APIClient()
    response = login(client, email, password)
    assert response.status_code == 200, response.content
    return client


def audit_events(event_type=None):
    queryset = AuditLog.objects.order_by("id")
    if event_type is not None:
        queryset = queryset.filter(event_type=event_type)
    return list(queryset)


def all_audit_text() -> str:
    """Everything stored in the audit table, to assert secrets never end up there."""
    return " ".join(
        f"{e.event_type} {e.target_id} {e.metadata} {e.ip_address}" for e in AuditLog.objects.all()
    )
