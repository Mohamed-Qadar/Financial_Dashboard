import pytest
from django.contrib.sessions.models import Session
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.tests.conftest import (
    NEW_PASSWORD,
    PASSWORD,
    all_audit_text,
    audit_events,
    logged_in_client,
    login,
)
from apps.audit.events import AuditEvent, Outcome

pytestmark = pytest.mark.django_db


def _change(client, current=PASSWORD, new=NEW_PASSWORD):
    return client.post(
        reverse("auth-password-change"),
        {"current_password": current, "new_password": new},
        format="json",
    )


def test_password_change_keeps_this_session_and_ends_all_others(user):
    current = logged_in_client()
    other_device = logged_in_client()
    old_key = current.cookies["sessionid"].value

    response = _change(current)

    assert response.status_code == 204
    # The session that changed the password keeps working, under a new session key.
    assert current.get(reverse("auth-me")).status_code == 200
    assert current.cookies["sessionid"].value != old_key
    assert not Session.objects.filter(session_key=old_key).exists()
    # Every other session is rejected.
    response = other_device.get(reverse("auth-me"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"


def test_new_password_works_and_old_one_does_not(user):
    _change(logged_in_client())

    assert login(APIClient(), "hodan@example.com", NEW_PASSWORD).status_code == 200
    assert login(APIClient(), "hodan@example.com", PASSWORD).status_code == 400


def test_password_change_is_audited_without_passwords(user):
    _change(logged_in_client())

    [event] = audit_events(AuditEvent.PASSWORD_CHANGED)
    assert (event.outcome, event.actor_id) == (Outcome.SUCCESS, user.pk)
    assert PASSWORD not in all_audit_text()
    assert NEW_PASSWORD not in all_audit_text()


def test_wrong_current_password_is_rejected_and_audited(user):
    client = logged_in_client()

    response = _change(client, current="Not-The-Password-1")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_current_password"
    user.refresh_from_db()
    assert user.check_password(PASSWORD)
    [event] = audit_events(AuditEvent.PASSWORD_CHANGE_FAILED)
    assert event.metadata == {"reason": "invalid_current_password"}
    assert client.get(reverse("auth-me")).status_code == 200


@pytest.mark.parametrize("weak", ["short", "1234567890123", "hodan@example.com", "password1234"])
def test_weak_new_password_is_rejected(user, weak):
    response = _change(logged_in_client(), new=weak)

    assert response.status_code == 400
    assert "new_password" in response.json()["error"]["details"]
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_password_change_requires_authentication(api):
    response = _change(api)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"
