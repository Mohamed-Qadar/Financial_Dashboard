import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.tests.conftest import NEW_PASSWORD, PASSWORD, login

pytestmark = pytest.mark.django_db


@pytest.fixture
def strict() -> APIClient:
    """A client that does not skip CSRF checks (the default test client does)."""
    return APIClient(enforce_csrf_checks=True)


def _csrf_token(client: APIClient) -> str:
    response = client.get(reverse("auth-csrf"))
    assert response.status_code == 204
    return client.cookies["csrftoken"].value


def _assert_csrf_failure(response):
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "csrf_failed"
    assert error["request_id"] == response["X-Request-ID"]


def test_csrf_endpoint_sets_a_readable_cookie(strict):
    response = strict.get(reverse("auth-csrf"))

    cookie = response.cookies["csrftoken"]
    assert cookie.value
    assert not cookie["httponly"]  # the frontend must read it to send X-CSRFToken
    assert cookie["samesite"] == "Lax"


def test_login_without_csrf_token_is_rejected(strict, user):
    """Login CSRF: an attacker's page must not be able to log the victim into another account."""
    _assert_csrf_failure(login(strict, "hodan@example.com", PASSWORD))


def test_login_with_csrf_token_succeeds(strict, user):
    token = _csrf_token(strict)

    response = login(strict, "hodan@example.com", PASSWORD, HTTP_X_CSRFTOKEN=token)

    assert response.status_code == 200


def test_login_from_a_foreign_origin_is_rejected(strict, user):
    token = _csrf_token(strict)

    response = login(
        strict,
        "hodan@example.com",
        PASSWORD,
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="https://evil.example",
    )

    _assert_csrf_failure(response)


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("auth-logout", {}),
        ("auth-password-change", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
    ],
)
def test_authenticated_unsafe_requests_need_the_token(strict, user, name, payload):
    token = _csrf_token(strict)
    assert login(strict, "hodan@example.com", PASSWORD, HTTP_X_CSRFTOKEN=token).status_code == 200

    response = strict.post(reverse(name), payload, format="json")

    _assert_csrf_failure(response)
    assert strict.get(reverse("auth-me")).status_code == 200  # still logged in


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("auth-password-reset", {"email": "hodan@example.com"}),
        ("auth-password-reset-confirm", {"uid": "x", "token": "y", "new_password": NEW_PASSWORD}),
    ],
)
def test_anonymous_unsafe_requests_need_the_token(strict, name, payload):
    _assert_csrf_failure(strict.post(reverse(name), payload, format="json"))
