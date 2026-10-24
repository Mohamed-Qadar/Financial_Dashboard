"""Audit entries cannot be changed through the ORM, the runtime role, or plain SQL."""

import psycopg
import pytest
from django.db import ProgrammingError, connection, transaction

from apps.audit.events import AuditEvent, Outcome
from apps.audit.models import AuditLog, ImmutableAuditLogError
from apps.audit.services import record_event
from apps.core.testing import app_role_connection

EVENT = AuditEvent.DB_RUNTIME_ROLE_ENSURED

INSERT_AS_APP = """
    INSERT INTO audit_logs (event_type, outcome, actor_type, target_type, target_id, metadata)
    VALUES (%s, 'failure', 'anonymous', '', '', '{}'::jsonb)
    RETURNING id
"""


@pytest.fixture
def entry(db):
    with transaction.atomic():
        return record_event(EVENT, Outcome.SUCCESS, system=True)


# --- ORM guards --------------------------------------------------------------------------


def test_orm_refuses_to_update_an_instance(entry):
    entry.outcome = Outcome.FAILURE
    with pytest.raises(ImmutableAuditLogError):
        entry.save()


def test_orm_refuses_to_delete(entry):
    with pytest.raises(ImmutableAuditLogError):
        entry.delete()
    with pytest.raises(ImmutableAuditLogError):
        AuditLog.objects.filter(pk=entry.pk).delete()


def test_orm_refuses_queryset_and_bulk_updates(entry):
    with pytest.raises(ImmutableAuditLogError):
        AuditLog.objects.filter(pk=entry.pk).update(outcome=Outcome.FAILURE)
    with pytest.raises(ImmutableAuditLogError):
        AuditLog.objects.bulk_update([entry], ["outcome"])


# --- trigger: applies even to the owner role --------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_logs SET outcome = 'failure' WHERE id = %s",
        "UPDATE audit_logs SET metadata = '{}'::jsonb, occurred_at = now() WHERE id = %s",
        "DELETE FROM audit_logs WHERE id = %s",
    ],
)
def test_trigger_blocks_changes_by_the_owner_role(entry, statement):
    with (
        pytest.raises(ProgrammingError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(statement, [entry.pk])

    assert AuditLog.objects.get(pk=entry.pk).outcome == Outcome.SUCCESS


# --- real login as the runtime role (somali_erp_app) ------------------------------------


@pytest.mark.django_db(transaction=True)
def test_runtime_role_can_append_and_read():
    with app_role_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT current_user")
        assert cursor.fetchone() == ("somali_erp_app",)
        cursor.execute(INSERT_AS_APP, [EVENT.value])
        [new_id] = cursor.fetchone()
        cursor.execute("SELECT event_type FROM audit_logs WHERE id = %s", [new_id])
        assert cursor.fetchone() == (EVENT.value,)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_logs SET outcome = 'success'",
        "UPDATE audit_logs SET metadata = '{}'::jsonb WHERE id = %(id)s",
        "DELETE FROM audit_logs WHERE id = %(id)s",
        "DELETE FROM audit_logs",
        "TRUNCATE audit_logs",
        "ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only",
        "ALTER TABLE audit_logs DISABLE TRIGGER ALL",
        "DROP TRIGGER audit_logs_append_only ON audit_logs",
        "DROP TABLE audit_logs",
        "CREATE OR REPLACE FUNCTION audit_logs_block_changes() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$",
        "SELECT setval(pg_get_serial_sequence('audit_logs', 'id'), 1)",
    ],
)
@pytest.mark.django_db(transaction=True)
def test_runtime_role_cannot_modify_or_remove_entries(statement):
    with app_role_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(INSERT_AS_APP, [EVENT.value])
            [entry_id] = cursor.fetchone()

        params = {"id": entry_id} if "%(id)s" in statement else None
        with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.cursor() as cursor:
            cursor.execute(statement, params)

        with conn.cursor() as cursor:
            cursor.execute("SELECT outcome FROM audit_logs WHERE id = %s", [entry_id])
            assert cursor.fetchone() == ("failure",)


@pytest.mark.django_db
def test_runtime_role_privileges_on_audit_table():
    def allowed(privilege):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT has_table_privilege('somali_erp_app', 'public.audit_logs', %s)",
                [privilege],
            )
            return cursor.fetchone()[0]

    assert allowed("SELECT") and allowed("INSERT")
    assert not any(allowed(p) for p in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"))
