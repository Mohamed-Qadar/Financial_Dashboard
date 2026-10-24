"""Grant the restricted runtime role (settings.DATABASE_APP_ROLE) its table privileges.

Creates the role as NOLOGIN if it does not exist yet; `manage.py ensure_db_roles` gives it a
password and enforces its attributes. Reversing revokes the grants and keeps the role.
"""

from django.db import migrations

from apps.core.db_roles import app_role, grant_sql, revoke_sql


def grant(apps, schema_editor):
    for statement in grant_sql(app_role()):
        # params=None: the SQL contains format('%I', ...), which must not be read as a placeholder.
        schema_editor.execute(statement, params=None)


def revoke(apps, schema_editor):
    for statement in revoke_sql(app_role()):
        schema_editor.execute(statement, params=None)


class Migration(migrations.Migration):
    # Runs after every table that exists today, so "ALL TABLES" covers them; later tables are
    # covered by the default privileges set here.
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sessions", "0001_initial"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
