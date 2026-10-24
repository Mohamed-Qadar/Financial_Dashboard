"""Company-scoped requests with real transactions (``transaction=True``).

Normal tests run inside a test transaction, where ``atomic(durable=True)`` only creates a
savepoint and nothing is really committed or rolled back. These tests use the production
lifecycle: no outer transaction (ATOMIC_REQUESTS is off), the view's block is the outermost
transaction, and failure events are written after it has truly rolled back.
"""

import json
import logging
import uuid
from unittest import mock

import pytest
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from apps.audit.events import AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.core import tenancy
from apps.core.structured_logging import JSONFormatter, RequestIDFilter
from apps.organizations.models import Branch
from apps.organizations.tests.factories import World, build_world, signed_in

pytestmark = pytest.mark.django_db(transaction=True)

OWNER = settings.DATABASES["default"]["USER"]


@pytest.fixture
def world() -> World:
    return build_world()


def events(event_type) -> list[AuditLog]:
    return list(AuditLog.objects.filter(event_type=event_type).order_by("id"))


def assert_connection_is_clean() -> None:
    assert not connection.in_atomic_block
    with transaction.atomic():
        assert tenancy.current() == ("", "", OWNER)


def test_request_atomic_requests_stays_disabled():
    assert settings.DATABASES["default"]["ATOMIC_REQUESTS"] is False


def test_company_scoped_view_refuses_to_run_inside_another_transaction(world):
    """Why ATOMIC_REQUESTS must stay off: the view's transaction must be the outermost."""
    client = signed_in(world.alice)
    with pytest.raises(RuntimeError, match="durable"), transaction.atomic():
        client.get(reverse("company-active"), HTTP_X_COMPANY_ID=str(world.company_a1.pk))


def test_successful_selection_and_its_event_are_committed_together(world):
    response = signed_in(world.alice).post(
        reverse("company-select"), HTTP_X_COMPANY_ID=str(world.company_a1.pk)
    )

    assert response.status_code == 200
    [event] = events(AuditEvent.COMPANY_SELECTED)
    assert (event.outcome, event.tenant_id) == (Outcome.SUCCESS, world.tenant_a.pk)
    assert_connection_is_clean()


def test_selection_fails_closed_when_its_event_cannot_be_written(world):
    with mock.patch(
        "apps.organizations.views.record_event", side_effect=DatabaseError("audit insert failed")
    ):
        response = signed_in(world.alice).post(
            reverse("company-select"), HTTP_X_COMPANY_ID=str(world.company_a1.pk)
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    # No success entry; the failure is stored after the rollback, still with its tenant.
    [event] = events(AuditEvent.COMPANY_SELECTED)
    assert event.outcome == Outcome.FAILURE
    assert (event.tenant_id, event.company_id) == (world.tenant_a.pk, world.company_a1.pk)
    assert event.metadata == {"reason": "storage_unavailable"}
    assert_connection_is_clean()


def test_denied_access_is_stored_after_the_request_rolled_back(world):
    response = signed_in(world.alice).get(
        reverse("company-active"), HTTP_X_COMPANY_ID=str(world.company_b1.pk)
    )

    assert response.status_code == 404
    [event] = events(AuditEvent.COMPANY_ACCESS_DENIED)
    assert (event.outcome, event.tenant_id) == (Outcome.DENIED, None)
    assert_connection_is_clean()


def test_denied_access_when_the_audit_table_is_unavailable(world, caplog):
    caplog.set_level(logging.CRITICAL, logger="apps.audit")
    leaky_error = DatabaseError(
        'DETAIL:  Failing row contains (203.0.113.7, {"reason": "not_accessible"}).'
    )
    with mock.patch("apps.audit.services._insert", side_effect=leaky_error):
        response = signed_in(world.alice).get(
            reverse("company-active"), HTTP_X_COMPANY_ID=str(world.company_b1.pk)
        )

    assert response.status_code == 404  # unchanged: the access is denied either way
    [record] = [r for r in caplog.records if r.name == "apps.audit"]
    assert record.levelno == logging.CRITICAL
    assert record.exc_info is None
    RequestIDFilter().filter(record)
    line = json.loads(JSONFormatter().format(record))
    assert line["audit_event"] == "tenancy.company_access_denied"
    assert line["audit_request_id"] == response["X-Request-ID"]
    text = json.dumps(line)
    for secret in ("Failing row", "203.0.113.7", str(world.company_b1.pk), "alice@example.com"):
        assert secret not in text
    assert_connection_is_clean()


def test_denied_access_when_the_rate_limit_store_is_unavailable(world, caplog):
    caplog.set_level(logging.ERROR, logger="apps.organizations.access")
    with mock.patch(
        "apps.organizations.access.enforce", side_effect=DatabaseError("counter unavailable")
    ):
        response = signed_in(world.alice).get(
            reverse("company-active"), HTTP_X_COMPANY_ID=str(world.company_b1.pk)
        )

    assert response.status_code == 404
    assert len(events(AuditEvent.COMPANY_ACCESS_DENIED)) == 1  # still audited
    [record] = [r for r in caplog.records if r.name == "apps.organizations.access"]
    assert record.error_type == "DatabaseError"
    assert "counter unavailable" not in record.getMessage()


@pytest.mark.urls("apps.organizations.tests.urls")
def test_failed_request_rolls_back_its_writes(world):
    client = signed_in(world.alice)
    response = client.post(
        reverse("test-create-branch") + "?fail=1",
        {"code": "NO"},
        format="json",
        HTTP_X_COMPANY_ID=str(world.company_a1.pk),
    )

    assert response.status_code == 400
    assert not Branch.objects.filter(code="NO").exists()
    assert_connection_is_clean()


def test_consecutive_requests_for_different_tenants_on_one_connection(world):
    client = signed_in(world.carol)
    connection.ensure_connection()
    backend_pid = connection.connection.info.backend_pid

    seen = [
        client.get(reverse("company-active"), HTTP_X_COMPANY_ID=str(company.pk)).json()["id"]
        for company in (world.company_a1, world.company_b1, world.company_a1)
    ]
    denied = client.get(reverse("company-active"), HTTP_X_COMPANY_ID=str(uuid.uuid4()))

    assert seen == [str(world.company_a1.pk), str(world.company_b1.pk), str(world.company_a1.pk)]
    assert denied.status_code == 404
    assert connection.connection.info.backend_pid == backend_pid  # really the same connection
    assert_connection_is_clean()
