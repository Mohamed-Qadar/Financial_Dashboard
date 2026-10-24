"""SQL functions that RLS policies use to read the request's tenant and user (apps.core.tenancy).

Plain SECURITY INVOKER functions: they only read the caller's own transaction settings and
bypass nothing. An unset or cleared setting ('' after its transaction ended) becomes NULL,
which matches no row, so a missing context fails closed.
"""

from django.db import migrations

from apps.core.db_roles import app_role

FUNCTIONS = {
    "app_current_tenant_id": "app.tenant_id",
    "app_current_user_id": "app.user_id",
}


def create_sql(name: str, setting: str) -> str:
    return (
        f"CREATE FUNCTION {name}() RETURNS uuid LANGUAGE sql STABLE "
        f"AS $$ SELECT NULLIF(current_setting('{setting}', true), '')::uuid $$"
    )


def grant_execute(apps, schema_editor):
    # Functions are executable by PUBLIC by default; only the runtime role (and the owner,
    # which owns them) needs them.
    for name in FUNCTIONS:
        schema_editor.execute(f"REVOKE EXECUTE ON FUNCTION {name}() FROM PUBLIC", params=None)
        schema_editor.execute(
            f'GRANT EXECUTE ON FUNCTION {name}() TO "{app_role()}"', params=None
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_rate_limit_counters"),
    ]

    operations = [
        *(
            migrations.RunSQL([create_sql(name, setting)], [f"DROP FUNCTION {name}()"])
            for name, setting in FUNCTIONS.items()
        ),
        migrations.RunPython(grant_execute, migrations.RunPython.noop),
    ]
