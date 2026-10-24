from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql

from apps.audit.events import AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.audit.services import record_event
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

        # Role change and its audit entry commit together or not at all.
        with transaction.atomic():
            before = self._privileged_attributes(role)
            exists = before is not None

            statement = sql.SQL(
                "{verb} ROLE {role} WITH LOGIN PASSWORD {password} {attributes}"
            ).format(
                verb=sql.SQL("ALTER" if exists else "CREATE"),
                role=sql.Identifier(role),
                password=sql.Literal(password),
                attributes=sql.SQL(APP_ROLE_ATTRIBUTES),
            )
            # Executed on the raw driver cursor so the password never reaches Django's query
            # log. Same connection, so it is part of the surrounding transaction.
            with connection.connection.cursor() as raw_cursor:
                raw_cursor.execute(statement)

            after = self._privileged_attributes(role)
            if after is None or any(after.values()) or not self._can_login(role):
                raise CommandError(f"Role {role} does not have the required restricted attributes.")

            action = "updated" if exists else "created"
            restored = sorted(name for name, value in (before or {}).items() if value)
            self._audit(role, action, restored)

        self.stdout.write(f"{action.capitalize()} runtime database role {role} (restricted).")
        if restored:
            self.stdout.write(f"Removed unexpected attributes: {', '.join(restored)}.")

    @staticmethod
    def _privileged_attributes(role: str) -> dict[str, bool] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication "
                "FROM pg_roles WHERE rolname = %s",
                [role],
            )
            row = cursor.fetchone()
        if row is None:
            return None
        names = ("superuser", "bypassrls", "createdb", "createrole", "replication")
        return dict(zip(names, row, strict=True))

    @staticmethod
    def _can_login(role: str) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", [role])
            return cursor.fetchone()[0]

    def _audit(self, role: str, action: str, restored: list[str]) -> None:
        # Before the first migration the audit table does not exist yet (fresh database).
        if AuditLog._meta.db_table not in connection.introspection.table_names():
            self.stderr.write("Audit table not found (run migrate first); event not recorded.")
            return
        record_event(
            AuditEvent.DB_RUNTIME_ROLE_ENSURED,
            Outcome.SUCCESS,
            system=True,
            target_type="db_role",
            target_id=role,
            metadata={"action": action, "restored_attributes": restored},
        )
