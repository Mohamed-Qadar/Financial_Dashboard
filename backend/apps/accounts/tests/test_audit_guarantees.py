"""Successes are audited in the same transaction; failures after rollback; nothing is dropped."""

import json
import logging
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import DatabaseError, transaction
from django.urls import reverse

from apps.accounts.tests.conftest import (
    NEW_PASSWORD,
    PASSWORD,
    audit_events,
    logged_in_client,
    login,
)
from apps.audit.events import AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.audit.services import record_failure_event
from apps.core.structured_logging import JSONFormatter, RequestIDFilter

pytestmark = pytest.mark.django_db

User = get_user_model()


def _fail_success_audit():
    """Make the SUCCESS audit write inside the views fail like a database error."""
    return mock.patch(
        "apps.accounts.views.record_event", side_effect=DatabaseError("audit insert failed")
    )


# --- success path: operation and audit commit or roll back together ----------------------


def test_login_is_refused_when_its_audit_entry_cannot_be_written(api, user):
    with _fail_success_audit():
        response = login(api, "hodan@example.com", PASSWORD)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    # No authenticated session survives, and nothing from the login was committed.
    assert api.get(reverse("auth-me")).status_code == 403
    user.refresh_from_db()
    assert user.last_login is None
    assert audit_events(AuditEvent.LOGIN_SUCCEEDED) == []
    # The failure itself is recorded afterwards.
    [event] = audit_events(AuditEvent.LOGIN_FAILED)
    assert event.metadata == {"reason": "storage_unavailable"}


def test_session_failure_after_audit_rolls_back_the_success_event(api, user):
    """The reverse direction: if the login itself fails, its success event disappears."""
    with mock.patch("apps.accounts.views.login", side_effect=DatabaseError("session write")):
        response = login(api, "hodan@example.com", PASSWORD)

    assert response.status_code == 503
    assert audit_events(AuditEvent.LOGIN_SUCCEEDED) == []
    assert [e.metadata["reason"] for e in audit_events(AuditEvent.LOGIN_FAILED)] == [
        "storage_unavailable"
    ]
    assert api.get(reverse("auth-me")).status_code == 403


def test_password_is_not_changed_without_its_audit_entry(user):
    client = logged_in_client()

    with _fail_success_audit():
        response = client.post(
            reverse("auth-password-change"),
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
        )

    assert response.status_code == 503
    user.refresh_from_db()
    assert user.check_password(PASSWORD)
    assert audit_events(AuditEvent.PASSWORD_CHANGED) == []
    [event] = audit_events(AuditEvent.PASSWORD_CHANGE_FAILED)
    assert event.metadata == {"reason": "storage_unavailable"}


def test_logout_is_refused_when_its_audit_entry_cannot_be_written(user):
    client = logged_in_client()

    with _fail_success_audit():
        response = client.post(reverse("auth-logout"))

    assert response.status_code == 503
    assert client.get(reverse("auth-me")).status_code == 200


def test_reset_email_is_not_sent_without_its_audit_entry(
    api, user, django_capture_on_commit_callbacks
):
    with _fail_success_audit(), django_capture_on_commit_callbacks(execute=True):
        response = api.post(
            reverse("auth-password-reset"), {"email": "hodan@example.com"}, format="json"
        )

    assert response.status_code == 202  # unchanged, so failures reveal nothing
    assert mail.outbox == []
    [event] = audit_events(AuditEvent.PASSWORD_RESET_REQUESTED)
    assert (event.outcome, event.metadata) == (Outcome.FAILURE, {"reason": "storage_unavailable"})


# --- failure path: written after the rollback, in its own transaction --------------------


def test_failure_events_cannot_be_recorded_inside_an_open_transaction(user):
    with pytest.raises(RuntimeError), transaction.atomic():
        record_failure_event(AuditEvent.LOGIN_FAILED, metadata={"reason": "x"})


def test_failure_event_survives_when_the_failed_operation_rolled_back(user):
    try:
        with transaction.atomic():
            User.objects.filter(pk=user.pk).update(full_name="Changed")
            raise DatabaseError("operation failed")
    except DatabaseError:
        record_failure_event(AuditEvent.PASSWORD_CHANGE_FAILED, metadata={"reason": "x"})

    user.refresh_from_db()
    assert user.full_name == "Hodan Ali"
    assert len(audit_events(AuditEvent.PASSWORD_CHANGE_FAILED)) == 1


# --- audit storage itself failing: logged at CRITICAL, never silently dropped -------------


def test_unstorable_failure_event_is_logged_critical_and_response_is_unchanged(api, user, caplog):
    caplog.set_level(logging.CRITICAL, logger="apps.audit")

    with mock.patch.object(
        AuditLog.objects, "create", side_effect=DatabaseError("audit table unavailable")
    ):
        response = login(api, "hodan@example.com", "Typed-Secret-9")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_credentials"
    [record] = [r for r in caplog.records if r.name == "apps.audit"]
    assert record.levelno == logging.CRITICAL
    assert record.audit_event == AuditEvent.LOGIN_FAILED
    assert record.audit_outcome == Outcome.FAILURE
    assert record.audit_request_id == response["X-Request-ID"]
    # The JSON log line carries the event but no credentials.
    RequestIDFilter().filter(record)
    line = JSONFormatter().format(record)
    assert json.loads(line)["audit_event"] == "auth.login_failed"
    assert "Typed-Secret-9" not in line
    assert "hodan@example.com" not in line


def test_programming_errors_in_failure_events_are_not_swallowed(user):
    with pytest.raises(ValueError):
        record_failure_event("auth.not_in_catalog")
    with pytest.raises(ValueError):
        record_failure_event(AuditEvent.LOGIN_FAILED, Outcome.SUCCESS)
