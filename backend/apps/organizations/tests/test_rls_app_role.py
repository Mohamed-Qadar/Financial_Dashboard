"""Row-level security, tested through a real login as the runtime role (somali_erp_app).

Every test here uses ``app_role_connection()``: the same role, privileges and policies as the
web process. Test data is created and committed on the owner connection first. Each check
runs in its own transaction that is always rolled back.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest

from apps.audit.events import AuditEvent, Outcome
from apps.audit.services import record_event
from apps.core.testing import app_role_connection
from apps.organizations.tests.factories import World, build_world

pytestmark = pytest.mark.django_db(transaction=True)

TENANT_TABLES = ("tenants", "memberships", "companies", "branches", "audit_logs")
RLS_VIOLATION = "row-level security"


@pytest.fixture
def world() -> World:
    world = build_world()
    record_event(AuditEvent.LOGIN_FAILED, Outcome.FAILURE)  # platform entry (no tenant)
    for tenant in (world.tenant_a, world.tenant_b):
        record_event(AuditEvent.LOGIN_FAILED, Outcome.FAILURE, tenant_id=tenant.pk)
    return world


@pytest.fixture
def app_conn() -> Iterator[psycopg.Connection]:
    with app_role_connection() as conn:
        yield conn


@contextmanager
def stage(conn, *, tenant=None, user=None) -> Iterator[psycopg.Cursor]:
    """One transaction in the given stage (like apps.core.tenancy), always rolled back."""
    with conn.transaction(force_rollback=True), conn.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true), set_config('app.user_id', %s, true)",
            [str(tenant or ""), str(user or "")],
        )
        yield cursor


def ids(cursor, query: str, params=None) -> set:
    cursor.execute(query, params)
    return {row[0] for row in cursor.fetchall()}


# --- reading ------------------------------------------------------------------------------


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_without_context_no_tenant_rows_are_visible(world, app_conn, table):
    with stage(app_conn) as cursor:
        cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed table names
        assert cursor.fetchone() == (0,)


def test_tenant_stage_sees_only_its_own_tenant(world, app_conn):
    w = world
    with stage(app_conn, tenant=w.tenant_a.pk) as cursor:
        assert ids(cursor, "SELECT id FROM tenants") == {w.tenant_a.pk}
        assert ids(cursor, "SELECT id FROM companies") == {w.company_a1.pk, w.company_a2.pk}
        assert ids(cursor, "SELECT id FROM branches") == {w.branch_a1.pk}
        assert ids(cursor, "SELECT DISTINCT tenant_id FROM memberships") == {w.tenant_a.pk}
        assert ids(cursor, "SELECT user_id FROM memberships") == {w.alice.pk, w.carol.pk}
        # Platform entries (tenant_id NULL) are not readable in any stage.
        assert ids(cursor, "SELECT tenant_id FROM audit_logs") == {w.tenant_a.pk}


def test_user_stage_sees_only_tenants_with_an_active_membership(world, app_conn):
    w = world
    with stage(app_conn, user=w.alice.pk) as cursor:
        # A (active) and S (active membership; the tenant's suspension is checked by the
        # application). Not B (no membership), not C (membership disabled).
        assert ids(cursor, "SELECT id FROM tenants") == {w.tenant_a.pk, w.tenant_s.pk}
        assert ids(cursor, "SELECT id FROM companies") == {
            w.company_a1.pk,
            w.company_a2.pk,
            w.company_s1.pk,
        }
        assert ids(cursor, "SELECT tenant_id FROM memberships") == {w.tenant_a.pk, w.tenant_s.pk}
        assert ids(cursor, "SELECT user_id FROM memberships") == {w.alice.pk}
        assert ids(cursor, "SELECT id FROM branches") == set()
        assert ids(cursor, "SELECT id FROM audit_logs") == set()

    with stage(app_conn, user=w.bob.pk) as cursor:
        assert ids(cursor, "SELECT id FROM companies") == {w.company_b1.pk}


def test_settings_end_with_the_transaction_on_a_reused_connection(world, app_conn):
    with app_conn.transaction(), app_conn.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(world.tenant_a.pk)])
        cursor.execute("SELECT count(*) FROM companies")
        assert cursor.fetchone() == (2,)

    with app_conn.transaction(), app_conn.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        assert cursor.fetchone() == ("",)  # NULLIF in app_current_tenant_id() handles this
        cursor.execute("SELECT count(*) FROM companies")
        assert cursor.fetchone() == (0,)


# --- writing --------------------------------------------------------------------------------


def _insert_statements(w: World) -> dict[str, tuple[str, list]]:
    """One INSERT ... RETURNING per table, for a row of tenant A."""
    a, a1 = str(w.tenant_a.pk), str(w.company_a1.pk)
    return {
        "tenants": (
            "INSERT INTO tenants (id, name, status, default_language, created_at, updated_at) "
            "VALUES (%s, 'X', 'active', 'so', now(), now()) RETURNING *",
            [a],  # same id: violates the primary key only if RLS lets it through
        ),
        "memberships": (
            "INSERT INTO memberships (id, tenant_id, user_id, status, is_owner, created_at, "
            "updated_at) VALUES (gen_random_uuid(), %s, %s, 'active', false, now(), now()) "
            "RETURNING *",
            [a, str(w.bob.pk)],
        ),
        "companies": (
            "INSERT INTO companies (id, tenant_id, code, legal_name, trade_name, "
            "base_currency_code, country_code, tax_id, timezone, fiscal_year_start_month, "
            "is_active, created_at, updated_at) VALUES (gen_random_uuid(), %s, 'NEW', 'New', "
            "'', 'USD', 'SO', '', 'Africa/Mogadishu', 1, true, now(), now()) RETURNING *",
            [a],
        ),
        "branches": (
            "INSERT INTO branches (id, tenant_id, company_id, code, name, address, phone, "
            "is_active, created_at, updated_at) VALUES (gen_random_uuid(), %s, %s, 'NEW', "
            "'New', '', '', true, now(), now()) RETURNING *",
            [a, a1],
        ),
        "audit_logs": (
            "INSERT INTO audit_logs (event_type, outcome, actor_type, tenant_id, target_type, "
            "target_id, metadata) VALUES ('auth.login_failed', 'failure', 'anonymous', %s, '', "
            "'', '{}'::jsonb) RETURNING *",
            [a],
        ),
    }


@pytest.mark.parametrize("table", ["memberships", "companies", "branches", "audit_logs"])
def test_insert_returning_works_in_the_rows_own_tenant_stage(world, app_conn, table):
    query, params = _insert_statements(world)[table]
    with stage(app_conn, tenant=world.tenant_a.pk) as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
        assert row is not None


def test_a_new_tenant_is_inserted_and_returned_in_its_own_tenant_stage(app_conn):
    new_tenant = uuid.uuid4()
    with stage(app_conn, tenant=new_tenant) as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name, status, default_language, created_at, updated_at) "
            "VALUES (%s, 'New', 'active', 'so', now(), now()) RETURNING id",
            [str(new_tenant)],
        )
        assert cursor.fetchone() == (new_tenant,)


@pytest.mark.parametrize("table", TENANT_TABLES)
@pytest.mark.parametrize("context", ["none", "user_stage", "other_tenant"])
def test_insert_is_rejected_outside_the_rows_tenant_stage(world, app_conn, table, context):
    query, params = _insert_statements(world)[table]
    tenant, user = {
        "none": (None, None),
        "user_stage": (None, world.alice.pk),
        "other_tenant": (world.tenant_b.pk, None),
    }[context]
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege, match=RLS_VIOLATION),
        stage(app_conn, tenant=tenant, user=user) as cursor,
    ):
        cursor.execute(query, params)


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE companies SET tenant_id = %(b)s WHERE id = %(a1)s",
        "UPDATE branches SET tenant_id = %(b)s WHERE company_id = %(a1)s",
        "UPDATE memberships SET tenant_id = %(b)s WHERE tenant_id = %(a)s",
        "UPDATE tenants SET id = %(b_new)s WHERE id = %(a)s",
    ],
)
def test_rows_cannot_be_moved_to_another_tenant(world, app_conn, query):
    params = {
        "a": world.tenant_a.pk,
        "a1": world.company_a1.pk,
        "b": world.tenant_b.pk,
        "b_new": uuid.uuid4(),
    }
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege, match=RLS_VIOLATION),
        stage(app_conn, tenant=world.tenant_a.pk) as cursor,
    ):
        cursor.execute(query, params)


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE tenants SET name = 'x' WHERE id = %(b)s",
        "UPDATE companies SET legal_name = 'x' WHERE tenant_id = %(b)s",
        "UPDATE branches SET name = 'x' WHERE tenant_id = %(b)s",
        "UPDATE memberships SET status = 'disabled' WHERE tenant_id = %(b)s",
    ],
)
def test_other_tenants_rows_cannot_be_changed(world, app_conn, query):
    with stage(app_conn, tenant=world.tenant_a.pk) as cursor:
        cursor.execute(query, {"b": world.tenant_b.pk})
        assert cursor.rowcount == 0


def test_user_stage_cannot_change_the_users_own_memberships(world, app_conn):
    with stage(app_conn, user=world.alice.pk) as cursor:
        cursor.execute(
            "UPDATE memberships SET is_owner = true WHERE user_id = %s", [world.alice.pk]
        )
        assert cursor.rowcount == 0
        cursor.execute("UPDATE companies SET legal_name = 'x'")
        assert cursor.rowcount == 0


# --- privileges -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO currencies (code, name, symbol, minor_units) VALUES ('EUR', 'Euro', 'E', 2)",
        "UPDATE currencies SET minor_units = 0 WHERE code = 'USD'",
        "DELETE FROM currencies WHERE code = 'SOS'",
        "DELETE FROM tenants",
        "DELETE FROM memberships",
        "DELETE FROM companies",
        "DELETE FROM branches",
        "TRUNCATE companies",
    ],
)
def test_runtime_role_cannot_change_reference_data_or_delete_tenancy_rows(
    world, app_conn, statement
):
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        stage(app_conn, tenant=world.tenant_a.pk) as cursor,
    ):
        cursor.execute(statement)


def test_runtime_role_can_read_currencies(world, app_conn):
    with stage(app_conn) as cursor:
        assert {"USD"} <= ids(cursor, "SELECT code FROM currencies")


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE companies DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE companies NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY",
        "DROP POLICY tenant_isolation ON companies",
        "ALTER POLICY tenant_isolation ON companies USING (true)",
        "CREATE POLICY open_door ON companies USING (true)",
        "CREATE OR REPLACE FUNCTION app_current_tenant_id() RETURNS uuid "
        "LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$",
        "ALTER FUNCTION app_current_tenant_id() SECURITY DEFINER",
        "CREATE FUNCTION bypass() RETURNS bigint LANGUAGE sql SECURITY DEFINER "
        "AS $$ SELECT count(*) FROM companies $$",
    ],
)
def test_runtime_role_cannot_change_or_bypass_row_level_security(app_conn, statement):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), stage(app_conn) as cursor:
        cursor.execute(statement)


def test_session_settings_are_not_a_boundary_against_arbitrary_sql(world, app_conn):
    """Documents an accepted limitation (docs/SECURITY.md § 2, layer 3).

    Anyone who can run SQL as the runtime role can choose the tenant context. RLS protects
    against application bugs (a forgotten filter), not against SQL injection or a
    compromised application; those are covered by parameterized queries and the other layers.
    """
    with stage(app_conn) as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(world.tenant_b.pk)])
        assert ids(cursor, "SELECT id FROM companies") == {world.company_b1.pk}
