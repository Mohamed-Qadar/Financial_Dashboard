from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql

from apps.core.db_roles import APP_ROLE_ATTRIBUTES, app_role


class Command(BaseCommand):
    help = (
        "Create or update the restricted runtime database role and enforce its attributes. "
        "Run with DJANGO_DB_ROLE=owner. Safe to run repeatedly."
    )

    def handle(self, *args, **options):
        role = app_role()
        password = settings.DATABASE_APP_PASSWORD
        if not password:
            raise CommandError("POSTGRES_APP_PASSWORD is required.")
        if connection.settings_dict["USER"] == role:
            raise CommandError(
                "This command must run as the owner role (DJANGO_DB_ROLE=owner), "
                "not as the runtime role it manages."
            )

        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            exists = cursor.fetchone() is not None

        statement = sql.SQL(
            "{verb} ROLE {role} WITH LOGIN PASSWORD {password} {attributes}"
        ).format(
            verb=sql.SQL("ALTER" if exists else "CREATE"),
            role=sql.Identifier(role),
            password=sql.Literal(password),
            attributes=sql.SQL(APP_ROLE_ATTRIBUTES),
        )
        # Executed on the raw driver cursor so the password never reaches Django's query log.
        with connection.connection.cursor() as raw_cursor:
            raw_cursor.execute(statement)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, "
                "rolreplication FROM pg_roles WHERE rolname = %s",
                [role],
            )
            can_login, *privileged = cursor.fetchone()
        if not can_login or any(privileged):
            raise CommandError(f"Role {role} does not have the required restricted attributes.")

        action = "Updated" if exists else "Created"
        self.stdout.write(f"{action} runtime database role {role} (restricted, login enabled).")
