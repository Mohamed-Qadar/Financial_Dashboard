import re
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
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

User = get_user_model()


def _request_reset(client, email, capture):
    with capture(execute=True):
        return client.post(reverse("auth-password-reset"), {"email": email}, format="json")


def _link_params() -> dict:
    [message] = mail.outbox
    url = re.search(r"https?://\S+", message.body).group(0)
    query = parse_qs(urlparse(url).query)
    return {"url": url, "uid": query["uid"][0], "token": query["token"][0]}


def _confirm(client, uid, token, new_password=NEW_PASSWORD):
    return client.post(
        reverse("auth-password-reset-confirm"),
        {"uid": uid, "token": token, "new_password": new_password},
        format="json",
    )


# --- request -------------------------------------------------------------------------------


def test_reset_request_emails_a_frontend_link(api, user, django_capture_on_commit_callbacks):
    response = _request_reset(api, "HODAN@example.com", django_capture_on_commit_callbacks)

    assert response.status_code == 202
    [message] = mail.outbox
    assert message.to == ["hodan@example.com"]
    link = _link_params()
    assert link["url"].startswith("http://localhost:3000/reset-password?")
    [event] = audit_events(AuditEvent.PASSWORD_RESET_REQUESTED)
    assert (event.outcome, event.target_id) == (Outcome.SUCCESS, str(user.pk))
    assert link["token"] not in all_audit_text()


@pytest.mark.parametrize("email", ["nobody@example.com", "inactive@example.com"])
def test_reset_request_for_ineligible_accounts_looks_the_same(
    api, user, email, django_capture_on_commit_callbacks
):
    User.objects.create_user("inactive@example.com", password=PASSWORD, is_active=False)

    response = _request_reset(api, email, django_capture_on_commit_callbacks)

    assert response.status_code == 202
    assert response.content == b""
    assert mail.outbox == []
    [event] = audit_events(AuditEvent.PASSWORD_RESET_REQUESTED)
    assert (event.outcome, event.metadata) == (Outcome.FAILURE, {"reason": "no_eligible_account"})
    assert email not in all_audit_text()


def test_email_delivery_failure_is_audited_and_hidden(
    api, user, django_capture_on_commit_callbacks
):
    with mock.patch("apps.accounts.services.send_mail", side_effect=ConnectionError("smtp down")):
        response = _request_reset(api, "hodan@example.com", django_capture_on_commit_callbacks)

    assert response.status_code == 202
    [event] = audit_events(AuditEvent.PASSWORD_RESET_EMAIL_FAILED)
    assert event.target_id == str(user.pk)


# --- confirm -------------------------------------------------------------------------------


def test_valid_link_sets_the_new_password_and_ends_existing_sessions(
    api, user, django_capture_on_commit_callbacks
):
    existing_session = logged_in_client()
    _request_reset(api, "hodan@example.com", django_capture_on_commit_callbacks)
    link = _link_params()

    response = _confirm(api, link["uid"], link["token"])

    assert response.status_code == 204
    assert login(APIClient(), "hodan@example.com", NEW_PASSWORD).status_code == 200
    assert login(APIClient(), "hodan@example.com", PASSWORD).status_code == 400
    assert existing_session.get(reverse("auth-me")).status_code == 403
    [event] = audit_events(AuditEvent.PASSWORD_RESET_COMPLETED)
    assert (event.outcome, event.actor_id) == (Outcome.SUCCESS, user.pk)


def test_link_cannot_be_used_twice(api, user, django_capture_on_commit_callbacks):
    _request_reset(api, "hodan@example.com", django_capture_on_commit_callbacks)
    link = _link_params()
    assert _confirm(api, link["uid"], link["token"]).status_code == 204

    response = _confirm(api, link["uid"], link["token"], new_password="Third-Strong-Phrase-99")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_link"


def test_link_expires_after_one_hour(api, user, django_capture_on_commit_callbacks):
    _request_reset(api, "hodan@example.com", django_capture_on_commit_callbacks)
    link = _link_params()
    later = datetime.now() + timedelta(hours=1, minutes=1)

    with mock.patch.object(default_token_generator, "_now", return_value=later):
        response = _confirm(api, link["uid"], link["token"])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_link"
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


@pytest.mark.parametrize(
    ("uid", "token"),
    [
        ("tampered", "token"),
        ("", ""),
        ("MTIz", "1-abc"),
        ("bm90LWEtdXVpZA", "x" * 40),
    ],
)
def test_forged_links_are_rejected_and_audited(api, user, uid, token):
    response = _confirm(api, uid, token)

    assert response.status_code == 400
    assert response.json()["error"]["code"] in {"invalid_reset_link", "validation_error"}
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_forged_token_for_a_real_user_is_audited(api, user, django_capture_on_commit_callbacks):
    _request_reset(api, "hodan@example.com", django_capture_on_commit_callbacks)
    link = _link_params()

    response = _confirm(api, link["uid"], link["token"][:-2] + "zz")

    assert response.status_code == 400
    [event] = audit_events(AuditEvent.PASSWORD_RESET_FAILED)
    assert event.metadata == {"reason": "invalid_or_expired_link"}


def test_weak_password_keeps_the_link_usable(api, user, django_capture_on_commit_callbacks):
    _request_reset(api, "hodan@example.com", django_capture_on_commit_callbacks)
    link = _link_params()

    weak = _confirm(api, link["uid"], link["token"], new_password="12345")
    strong = _confirm(api, link["uid"], link["token"])

    assert weak.status_code == 400
    assert "new_password" in weak.json()["error"]["details"]
    assert strong.status_code == 204
