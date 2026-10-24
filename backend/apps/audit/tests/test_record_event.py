import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone

from apps.audit.events import ActorType, AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.audit.services import MAX_STRING_LENGTH, REDACTED, record_event
from apps.core.request_id import bind_request_id, unbind_request_id

pytestmark = pytest.mark.django_db

EVENT = AuditEvent.DB_RUNTIME_ROLE_ENSURED
REQUEST_ID = "3f2b8c1e-4d5a-4b6c-9e7f-0a1b2c3d4e5f"


def _request(user=None, remote_addr="203.0.113.7"):
    request = RequestFactory().get("/", REMOTE_ADDR=remote_addr)
    request.user = user or AnonymousUser()
    request.request_id = REQUEST_ID
    return request


@pytest.fixture
def user():
    return get_user_model().objects.create_user("auditor@example.com")


# --- what gets recorded ------------------------------------------------------------------


def test_records_all_context_fields(user):
    company_id, tenant_id = uuid.uuid4(), uuid.uuid4()

    entry = record_event(
        EVENT,
        Outcome.SUCCESS,
        request=_request(user),
        tenant_id=tenant_id,
        company_id=company_id,
        target_type="db_role",
        target_id="somali_erp_app",
        metadata={"action": "updated"},
    )

    entry = AuditLog.objects.get(pk=entry.pk)
    assert entry.event_type == EVENT
    assert entry.outcome == Outcome.SUCCESS
    assert (entry.actor_type, entry.actor_id) == (ActorType.USER, user.pk)
    assert (entry.tenant_id, entry.company_id) == (tenant_id, company_id)
    assert (entry.target_type, entry.target_id) == ("db_role", "somali_erp_app")
    assert str(entry.request_id) == REQUEST_ID
    assert entry.ip_address == "203.0.113.7"
    assert entry.metadata == {"action": "updated"}
    assert abs(entry.occurred_at - timezone.now()) < timedelta(minutes=1)


def test_system_and_anonymous_actors():
    system = record_event(EVENT, Outcome.SUCCESS, system=True)
    anonymous = record_event(EVENT, Outcome.FAILURE, request=_request())

    assert (system.actor_type, system.actor_id) == (ActorType.SYSTEM, None)
    assert (anonymous.actor_type, anonymous.actor_id) == (ActorType.ANONYMOUS, None)


def test_explicit_actor_wins_over_request_user(user):
    other = get_user_model().objects.create_user("other@example.com")

    entry = record_event(EVENT, Outcome.SUCCESS, request=_request(user), actor=other)

    assert entry.actor_id == other.pk


def test_request_id_falls_back_to_the_current_request():
    token = bind_request_id(REQUEST_ID)
    try:
        entry = record_event(EVENT, Outcome.SUCCESS, system=True)
    finally:
        unbind_request_id(token)

    assert str(entry.request_id) == REQUEST_ID


def test_invalid_remote_address_is_not_stored():
    entry = record_event(EVENT, Outcome.FAILURE, request=_request(remote_addr="not-an-ip"))

    assert entry.ip_address is None


def test_unknown_event_or_outcome_is_rejected():
    with pytest.raises(ValueError):
        record_event("user.did_something_unlisted", Outcome.SUCCESS, system=True)
    with pytest.raises(ValueError):
        record_event(EVENT, "maybe", system=True)


# --- no secrets or unnecessary personal data --------------------------------------------


def test_sensitive_metadata_is_redacted_at_any_depth():
    entry = record_event(
        EVENT,
        Outcome.FAILURE,
        system=True,
        metadata={
            "Password": "hunter2",
            "new_password_confirm": "hunter2",
            "nested": {"api_token": "abc", "items": [{"client_secret": "x", "ok": 1}]},
            "sessionid": "s",
            "csrfToken": "c",
            "Authorization": "Bearer abc",
            "reason": "kept",
        },
    )

    stored = AuditLog.objects.get(pk=entry.pk).metadata
    assert stored == {
        "Password": REDACTED,
        "new_password_confirm": REDACTED,
        "nested": {"api_token": REDACTED, "items": [{"client_secret": REDACTED, "ok": 1}]},
        "sessionid": REDACTED,
        "csrfToken": REDACTED,
        "Authorization": REDACTED,
        "reason": "kept",
    }
    assert "hunter2" not in str(stored)


def test_metadata_values_are_made_json_safe_and_shortened():
    value_id = uuid.uuid4()

    entry = record_event(
        EVENT,
        Outcome.FAILURE,
        system=True,
        metadata={"amount": Decimal("12.50"), "id": value_id, "note": "x" * 2000},
    )

    stored = AuditLog.objects.get(pk=entry.pk).metadata
    assert stored["amount"] == "12.50"
    assert stored["id"] == str(value_id)
    assert len(stored["note"]) == MAX_STRING_LENGTH + 1


def test_oversized_metadata_is_rejected():
    with pytest.raises(ValueError, match="limit"):
        record_event(
            EVENT, Outcome.FAILURE, system=True, metadata={f"k{i}": "v" * 400 for i in range(20)}
        )


def test_long_target_id_is_truncated():
    entry = record_event(EVENT, Outcome.FAILURE, system=True, target_id="x" * 500)

    assert len(entry.target_id) == 64


# --- transactions ------------------------------------------------------------------------


def test_success_event_is_rolled_back_with_its_operation():
    with pytest.raises(RuntimeError, match="operation failed"), transaction.atomic():
        record_event(EVENT, Outcome.SUCCESS, system=True)
        raise RuntimeError("operation failed")

    assert AuditLog.objects.count() == 0


def test_success_event_commits_with_its_operation():
    with transaction.atomic():
        record_event(EVENT, Outcome.SUCCESS, system=True)

    assert AuditLog.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_success_event_outside_a_transaction_is_refused():
    with pytest.raises(RuntimeError, match=r"transaction\.atomic"):
        record_event(EVENT, Outcome.SUCCESS, system=True)

    assert AuditLog.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_failure_event_outside_a_transaction_is_committed():
    record_event(EVENT, Outcome.FAILURE, system=True)

    assert AuditLog.objects.count() == 1


def test_database_rejects_inconsistent_actor():
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditLog.objects.create(event_type=EVENT, outcome=Outcome.SUCCESS, actor_type="user")


# --- events emitted by this milestone ---------------------------------------------------


def test_ensure_db_roles_records_an_event():
    call_command("ensure_db_roles", stdout=StringIO())

    entry = AuditLog.objects.get()
    assert entry.event_type == AuditEvent.DB_RUNTIME_ROLE_ENSURED
    assert entry.outcome == Outcome.SUCCESS
    assert entry.actor_type == ActorType.SYSTEM
    assert entry.target_id == "somali_erp_app"
    assert entry.metadata == {"action": "updated", "restored_attributes": []}
    assert "password" not in str(entry.metadata).lower()


@pytest.mark.django_db(transaction=True)
def test_ensure_db_roles_records_restored_attributes():
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute('ALTER ROLE "somali_erp_app" CREATEDB')

    call_command("ensure_db_roles", stdout=StringIO())

    entry = AuditLog.objects.get()
    assert entry.metadata["restored_attributes"] == ["createdb"]
