"""The web process's database role must be unable to bypass row-level security or change schema."""

from unittest import mock

import psycopg
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.testing import app_role_connection, as_app_role

APP_ROLE = settings.DATABASE_APP_ROLE
OWNER_ROLE = settings.DATABASES["default"]["USER"]
DML = ("SELECT", "INSERT", "UPDATE", "DELETE")
# Tables the runtime role may only read and append to; each has its own privilege tests.
APPEND_ONLY_TABLES = {"audit_logs"}

pytestmark = pytest.mark.django_db


def _fetchall(query, params=None):
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


def test_app_role_has_no_elevated_attributes():
    [row] = _fetchall(
        "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication "
        "FROM pg_roles WHERE rolname = %s",
        [APP_ROLE],
    )
    assert row == (False, False, False, False, False)


def test_app_role_is_not_the_owner_and_owns_nothing():
    assert APP_ROLE != OWNER_ROLE
    owned = _fetchall(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = %s",
        [APP_ROLE],
    )
    assert owned == []


def test_app_role_has_dml_on_every_application_table():
    """Covers tables added by later migrations too (default privileges)."""
    tables = [
        name
        for (name,) in _fetchall("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        if name != "django_migrations" and name not in APPEND_ONLY_TABLES
    ]
    assert "users" in tables
    missing = [
        f"{table}:{privilege}"
        for table in tables
        for privilege in DML
        if not _fetchall(
            "SELECT has_table_privilege(%s, %s, %s)", [APP_ROLE, f"public.{table}", privilege]
        )[0][0]
    ]
    assert missing == []


def test_app_role_can_only_read_migration_history():
    def allowed(privilege):
        return _fetchall(
            "SELECT has_table_privilege(%s, 'public.django_migrations', %s)",
            [APP_ROLE, privilege],
        )[0][0]

    assert allowed("SELECT")
    assert not any(allowed(p) for p in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"))


def test_app_role_can_read_and_write_application_data():
    User = get_user_model()
    with as_app_role():
        user = User.objects.create_user("app-role@example.com", password="s3cure-pass-phrase")
        assert User.objects.filter(pk=user.pk).exists()
        User.objects.filter(pk=user.pk).update(full_name="Updated")
        User.objects.filter(pk=user.pk).delete()
        assert not User.objects.filter(pk=user.pk).exists()


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE attacker_table (id int)",
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN pwned int",
        "TRUNCATE users",
        "DELETE FROM django_migrations",
        "INSERT INTO django_migrations (app, name, applied) VALUES ('x', 'y', now())",
        f'SET ROLE "{OWNER_ROLE}"',
        f'ALTER ROLE "{APP_ROLE}" SUPERUSER',
        f'ALTER ROLE "{APP_ROLE}" BYPASSRLS',
        'CREATE ROLE "attacker_role" SUPERUSER',
    ],
)
@pytest.mark.django_db(transaction=True)
def test_app_role_cannot_escalate_or_change_schema(statement):
    # A real login as the app role, exactly like the web process. (Switching roles on an owner
    # connection cannot test this: SET ROLE is checked against the session user, the owner.)
    with app_role_connection() as app_conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), app_conn.cursor() as cursor:
            cursor.execute(statement)
        with app_conn.cursor() as cursor:
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == (APP_ROLE,)


def test_readiness_check_works_as_app_role():
    with as_app_role():
        response = APIClient().get(reverse("health-ready"))

    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_ensure_db_roles_is_idempotent_and_enables_login():
    call_command("ensure_db_roles", stdout=mock.MagicMock())
    call_command("ensure_db_roles", stdout=mock.MagicMock())

    with app_role_connection() as app_conn, app_conn.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
        )
        assert cursor.fetchone() == (APP_ROLE, False)


@pytest.mark.django_db(transaction=True)
def test_ensure_db_roles_restores_restricted_attributes():
    with connection.cursor() as cursor:
        cursor.execute(f'ALTER ROLE "{APP_ROLE}" CREATEDB')

    call_command("ensure_db_roles", stdout=mock.MagicMock())

    [(createdb,)] = _fetchall("SELECT rolcreatedb FROM pg_roles WHERE rolname = %s", [APP_ROLE])
    assert createdb is False


def test_ensure_db_roles_refuses_to_run_as_the_app_role():
    with (
        mock.patch.dict(connection.settings_dict, {"USER": APP_ROLE}),
        pytest.raises(CommandError, match="owner role"),
    ):
        call_command("ensure_db_roles")


def test_ensure_db_roles_requires_a_password(settings):
    settings.DATABASE_APP_PASSWORD = None

    with pytest.raises(CommandError, match="POSTGRES_APP_PASSWORD"):
        call_command("ensure_db_roles")
