import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.urls import reverse

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.accounts.tests.conftest import PASSWORD, all_audit_text, audit_events, login
from apps.audit.events import ActorType, AuditEvent, Outcome

pytestmark = pytest.mark.django_db

User = get_user_model()


def _body_without_request_id(response) -> dict:
    error = dict(response.json()["error"])
    error.pop("request_id")
    return error


# --- success ------------------------------------------------------------------------------


def test_login_succeeds_and_returns_the_user(api, user):
    response = login(api, "hodan@example.com", PASSWORD)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.pk),
        "email": "hodan@example.com",
        "full_name": "Hodan Ali",
        "preferred_language": "en",
    }
    assert api.get(reverse("auth-me")).json()["id"] == str(user.pk)


def test_session_cookie_is_httponly_lax_and_has_the_idle_lifetime(api, user):
    response = login(api, "hodan@example.com", PASSWORD)

    cookie = response.cookies["sessionid"]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert int(cookie["max-age"]) == 12 * 60 * 60


def test_email_is_case_and_whitespace_insensitive(api, user):
    response = login(api, "  HODAN@Example.com ", PASSWORD)

    assert response.status_code == 200


def test_login_records_audit_event_and_login_time(api, user):
    before = int(time.time())
    login(api, "hodan@example.com", PASSWORD, REMOTE_ADDR="203.0.113.5")

    [event] = audit_events(AuditEvent.LOGIN_SUCCEEDED)
    assert event.outcome == Outcome.SUCCESS
    assert (event.actor_type, event.actor_id) == (ActorType.USER, user.pk)
    assert event.target_id == str(user.pk)
    assert event.ip_address == "203.0.113.5"
    session = SessionStore(api.cookies["sessionid"].value)
    assert session[LOGIN_AT_SESSION_KEY] >= before
    user.refresh_from_db()
    assert user.last_login is not None


def test_login_rotates_the_session_key(api, user):
    """Session fixation: a session key known before login must not survive it."""
    planted = SessionStore()
    planted["planted"] = True
    planted.create()
    api.cookies["sessionid"] = planted.session_key

    login(api, "hodan@example.com", PASSWORD)

    assert api.cookies["sessionid"].value != planted.session_key
    assert not Session.objects.filter(session_key=planted.session_key).exists()


def test_old_password_hash_is_upgraded_to_argon2(api, user):
    User.objects.filter(pk=user.pk).update(password=make_password(PASSWORD, hasher="pbkdf2_sha256"))

    assert login(api, "hodan@example.com", PASSWORD).status_code == 200

    user.refresh_from_db()
    assert user.password.startswith("argon2")


def test_new_passwords_are_hashed_with_argon2(user):
    assert user.password.startswith("argon2")


# --- failures: identical answers, no enumeration -----------------------------------------


def test_unknown_email_wrong_password_and_inactive_account_look_identical(api, user):
    User.objects.create_user("inactive@example.com", password=PASSWORD, is_active=False)

    responses = [
        login(api, "nobody@example.com", PASSWORD),
        login(api, "hodan@example.com", "Wrong-Password-123"),
        login(api, "inactive@example.com", PASSWORD),
    ]

    assert {r.status_code for r in responses} == {400}
    bodies = [_body_without_request_id(r) for r in responses]
    assert (
        bodies[0]
        == bodies[1]
        == bodies[2]
        == {
            "code": "invalid_credentials",
            "message": "Invalid email or password.",
        }
    )
    assert all("sessionid" not in r.cookies for r in responses)


def test_failed_logins_are_audited_without_email_or_password(api, user):
    login(api, "nobody@example.com", "Typed-Secret-1")
    login(api, "hodan@example.com", "Typed-Secret-2")

    unknown, known = audit_events(AuditEvent.LOGIN_FAILED)
    assert (unknown.outcome, unknown.actor_type, unknown.target_id) == (
        Outcome.FAILURE,
        ActorType.ANONYMOUS,
        "",
    )
    assert known.target_id == str(user.pk)
    stored = all_audit_text()
    assert "nobody@example.com" not in stored
    assert "hodan@example.com" not in stored
    assert "Typed-Secret" not in stored


def test_account_without_usable_password_cannot_log_in(api):
    User.objects.create_user("nopass@example.com")

    assert login(api, "nopass@example.com", "").status_code == 400
    assert login(api, "nopass@example.com", "anything-at-all").json()["error"]["code"] == (
        "invalid_credentials"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "x"},
        {"email": "hodan@example.com"},
        {"email": "hodan@example.com", "password": "x" * 1025},
    ],
)
def test_malformed_input_is_rejected_before_hashing(api, user, payload):
    response = api.post(reverse("auth-login"), payload, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert audit_events(AuditEvent.LOGIN_FAILED) == []


# --- me / logout -------------------------------------------------------------------------


def test_me_requires_authentication(api):
    response = api.get(reverse("auth-me"))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"


def test_logout_ends_the_session_and_is_audited(api, user):
    login(api, "hodan@example.com", PASSWORD)
    session_key = api.cookies["sessionid"].value

    response = api.post(reverse("auth-logout"))

    assert response.status_code == 204
    assert api.get(reverse("auth-me")).status_code == 403
    assert not Session.objects.filter(session_key=session_key).exists()
    [event] = audit_events(AuditEvent.LOGOUT)
    assert event.actor_id == user.pk


def test_anonymous_logout_is_a_quiet_no_op(api):
    assert api.post(reverse("auth-logout")).status_code == 204
    assert audit_events(AuditEvent.LOGOUT) == []
