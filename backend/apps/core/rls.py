"""Migration operations for row-level security, composite keys and table privileges.

Every app uses these helpers so all tenant-owned tables get the same, reversible SQL.
Table, column and policy names are literals written in migrations (never user input).
Policies are not limited to a role: they apply to every role that is subject to RLS,
including the table owner (FORCE ROW LEVEL SECURITY). Superusers bypass RLS.
"""

from django.db import migrations

from apps.core.db_roles import app_role

TENANT_MATCH = "{column} = app_current_tenant_id()"
# Rows of tenants in which the user of the user stage has an active membership.
ACTIVE_MEMBER_OF = (
    "EXISTS (SELECT 1 FROM memberships m WHERE m.tenant_id = {column} "
    "AND m.user_id = app_current_user_id() AND m.status = 'active')"
)


def enable_rls(table: str) -> migrations.RunSQL:
    return migrations.RunSQL(
        [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        ],
        [
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        ],
    )


def policy(
    table: str,
    name: str,
    *,
    command: str = "ALL",
    using: str | None = None,
    check: str | None = None,
) -> migrations.RunSQL:
    clauses = [f"CREATE POLICY {name} ON {table} FOR {command}"]
    if using is not None:
        clauses.append(f"USING ({using})")
    if check is not None:
        clauses.append(f"WITH CHECK ({check})")
    return migrations.RunSQL([" ".join(clauses)], [f"DROP POLICY {name} ON {table}"])


def tenant_isolation(table: str, column: str = "tenant_id") -> migrations.RunSQL:
    """Read and write only rows of the tenant stage's tenant."""
    match = TENANT_MATCH.format(column=f"{table}.{column}")
    return policy(table, "tenant_isolation", using=match, check=match)


def visible_to_active_members(table: str, column: str = "tenant_id") -> migrations.RunSQL:
    """User stage: also read rows of tenants the user is an active member of (no writes)."""
    return policy(
        table,
        "active_member_read",
        command="SELECT",
        # Qualified with the table name: unqualified, the column would resolve to the
        # subquery's own memberships.tenant_id/id and match every tenant.
        using=ACTIVE_MEMBER_OF.format(column=f"{table}.{column}"),
    )


def composite_foreign_key(
    table: str, name: str, columns: tuple[str, ...], target: str, target_columns: tuple[str, ...]
) -> migrations.RunSQL:
    """Keep a reference inside one tenant. Checked immediately, deletes are restricted."""
    return migrations.RunSQL(
        [
            f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({', '.join(columns)}) "
            f"REFERENCES {target} ({', '.join(target_columns)}) ON DELETE RESTRICT"
        ],
        [f"ALTER TABLE {table} DROP CONSTRAINT {name}"],
    )


def revoke_from_app_role(table: str, privileges: str) -> migrations.RunPython:
    """Narrow the default privileges (core.0001) for one table; reversing grants them back."""

    def revoke(apps, schema_editor):
        schema_editor.execute(f'REVOKE {privileges} ON {table} FROM "{app_role()}"', params=None)

    def grant(apps, schema_editor):
        schema_editor.execute(f'GRANT {privileges} ON {table} TO "{app_role()}"', params=None)

    return migrations.RunPython(revoke, grant)
