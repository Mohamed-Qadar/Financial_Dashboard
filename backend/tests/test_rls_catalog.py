"""Catalog checks: row-level security and composite keys cannot be forgotten.

New tenant-owned tables (``TenantOwnedModel``) must enable and force RLS with a
``tenant_isolation`` policy, and every reference between tenant-owned tables must have a
composite foreign key on ``(tenant_id, <reference>)``.
"""

import pytest
from django.apps import apps
from django.db import connection

from apps.audit.models import AuditLog
from apps.tenants.models import Tenant, TenantOwnedModel

pytestmark = pytest.mark.django_db


def _tenant_owned_models():
    return [m for m in apps.get_models() if issubclass(m, TenantOwnedModel)]


def _query(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _rls_flags(table: str) -> tuple[bool, bool]:
    [(enabled, forced)] = _query(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = %s::regclass",
        [table],
    )
    return enabled, forced


def _policies(table: str) -> set[str]:
    return {
        name
        for (name,) in _query("SELECT policyname FROM pg_policies WHERE tablename = %s", [table])
    }


def test_tenant_owned_models_exist():
    assert {m._meta.db_table for m in _tenant_owned_models()} >= {
        "memberships",
        "companies",
        "branches",
    }


@pytest.mark.parametrize(
    "table",
    sorted({m._meta.db_table for m in _tenant_owned_models()} | {Tenant._meta.db_table}),
)
def test_tenant_tables_enable_and_force_rls_with_tenant_isolation(table):
    assert _rls_flags(table) == (True, True)
    assert "tenant_isolation" in _policies(table)


def test_audit_log_has_rls():
    assert _rls_flags(AuditLog._meta.db_table) == (True, True)
    assert _policies(AuditLog._meta.db_table) == {"tenant_read", "append"}


def test_every_table_with_a_tenant_column_has_rls():
    """Catches tenant tables that do not use TenantOwnedModel."""
    tables = [
        name
        for (name,) in _query(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'tenant_id'"
        )
    ]
    assert tables
    assert [t for t in tables if _rls_flags(t) != (True, True)] == []


def _composite_foreign_keys(table: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    rows = _query(
        """
        SELECT
            array(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(n, i)
                  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n ORDER BY k.i),
            c.confrelid::regclass::text,
            array(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(n, i)
                  JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n ORDER BY k.i)
        FROM pg_constraint c
        WHERE c.contype = 'f' AND c.conrelid = %s::regclass AND array_length(c.conkey, 1) > 1
        """,
        [table],
    )
    return {(tuple(cols), target, tuple(target_cols)) for cols, target, target_cols in rows}


def test_references_between_tenant_tables_have_composite_foreign_keys():
    expected, missing = [], []
    for model in _tenant_owned_models():
        for field in model._meta.concrete_fields:
            target = getattr(field, "related_model", None)
            if not field.is_relation or not issubclass(target, TenantOwnedModel):
                continue
            key = (("tenant_id", field.column), target._meta.db_table, ("tenant_id", "id"))
            expected.append(key)
            if key not in _composite_foreign_keys(model._meta.db_table):
                missing.append(f"{model._meta.db_table}.{field.column}")
    assert expected  # branches.company_id at least
    assert missing == []


def test_no_security_definer_functions():
    """Nothing bypasses RLS by running with its owner's rights (design decision, 2.3a)."""
    rows = _query(
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.prosecdef"
    )
    assert rows == []


@pytest.mark.parametrize("function", ["app_current_tenant_id", "app_current_user_id"])
def test_context_functions_are_not_executable_by_public(function):
    rows = _query(
        "SELECT a.grantee FROM pg_proc p, aclexplode(p.proacl) a "
        "WHERE p.proname = %s AND a.privilege_type = 'EXECUTE'",
        [function],
    )
    assert rows  # explicit ACL exists
    assert 0 not in {grantee for (grantee,) in rows}  # 0 = PUBLIC
