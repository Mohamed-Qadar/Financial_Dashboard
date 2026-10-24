"""The runtime role's privileges, table by table (least privilege).

Every table in the public schema must be listed here: a new table fails the test until its
privileges are decided. Read from the catalog; denials are also exercised with a real
runtime-role login in apps/organizations/tests/test_rls_app_role.py and
apps/audit/tests/test_immutability.py.
"""

import pytest
from django.conf import settings
from django.db import connection

APP_ROLE = settings.DATABASE_APP_ROLE
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

DML = {"SELECT", "INSERT", "UPDATE", "DELETE"}
# Archived or disabled, never deleted.
NO_DELETE = {"SELECT", "INSERT", "UPDATE"}

EXPECTED = {
    # Django and accounts
    "auth_group": DML,
    "auth_group_permissions": DML,
    "auth_permission": DML,
    "django_content_type": DML,
    "django_migrations": {"SELECT"},
    "django_session": DML,
    "users": DML,
    "users_groups": DML,
    "users_user_permissions": DML,
    # core: upsert counters, purge expired rows; no tenant data (HMAC keys only)
    "rate_limit_counters": DML,
    # audit: append-only
    "audit_logs": {"SELECT", "INSERT"},
    # finance: global reference data
    "currencies": {"SELECT"},
    # tenancy
    "tenants": NO_DELETE,
    "memberships": NO_DELETE,
    "companies": NO_DELETE,
    "branches": NO_DELETE,
}

pytestmark = pytest.mark.django_db


def _query(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def test_every_table_has_a_declared_privilege_set():
    tables = {
        name for (name,) in _query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }
    assert tables == set(EXPECTED)


@pytest.mark.parametrize("table", sorted(EXPECTED))
def test_runtime_role_has_exactly_the_declared_privileges(table):
    granted = {
        privilege
        for privilege in PRIVILEGES
        if _query(
            "SELECT has_table_privilege(%s, %s, %s)", [APP_ROLE, f"public.{table}", privilege]
        )[0][0]
    }
    assert granted == EXPECTED[table]


def test_runtime_role_cannot_set_any_sequence():
    """USAGE allows nextval(); UPDATE (setval) would let it reuse audit ids."""
    rows = _query(
        "SELECT c.relname, has_sequence_privilege(%s, c.oid, 'UPDATE') FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relkind = 'S' AND n.nspname = 'public'",
        [APP_ROLE],
    )
    assert rows
    assert [name for name, can_update in rows if can_update] == []


def test_runtime_role_owns_nothing_and_cannot_create_in_the_schema():
    assert _query("SELECT has_schema_privilege(%s, 'public', 'CREATE')", [APP_ROLE]) == [(False,)]
    owned = _query(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND pg_get_userbyid(c.relowner) = %s "
        "UNION ALL SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND pg_get_userbyid(p.proowner) = %s",
        [APP_ROLE, APP_ROLE],
    )
    assert owned == []
