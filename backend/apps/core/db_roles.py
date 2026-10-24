"""SQL for the restricted runtime database role (see docs/SECURITY.md, "Database roles").

The role name comes from settings.DATABASE_APP_ROLE, which settings validate as a plain
lower-case identifier, so it is safe to interpolate into the statements below.
"""

from django.conf import settings

# Attributes the runtime role must always have. Enforced on every ensure_db_roles run.
APP_ROLE_ATTRIBUTES = "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION"


def app_role() -> str:
    return settings.DATABASE_APP_ROLE


def create_role_if_missing_sql(role: str) -> str:
    # NOLOGIN until ensure_db_roles sets a password, so a fresh database never has a
    # passwordless login role. `role` is a validated identifier (see module docstring).
    return f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE "{role}" NOLOGIN {APP_ROLE_ATTRIBUTES};
            END IF;
        END
        $$;
    """


def grant_sql(role: str) -> list[str]:
    return [
        create_role_if_missing_sql(role),
        f"""DO $$ BEGIN
                EXECUTE format('GRANT CONNECT ON DATABASE %I TO "{role}"', current_database());
            END $$;""",
        f'GRANT USAGE ON SCHEMA public TO "{role}"',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"',
        f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"',
        # Tables and sequences created later by the migrating (owner) role get the same rights.
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "{role}"',
        # Migration history is owner business only.
        f'REVOKE INSERT, UPDATE, DELETE ON django_migrations FROM "{role}"',
    ]


def revoke_sql(role: str) -> list[str]:
    # The role itself is kept: dropping it could fail or break other databases in the cluster.
    return [
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM "{role}"',
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f'REVOKE USAGE, SELECT ON SEQUENCES FROM "{role}"',
        f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"',
        f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM "{role}"',
        f'REVOKE USAGE ON SCHEMA public FROM "{role}"',
        f"""DO $$ BEGIN
                EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM "{role}"', current_database());
            END $$;""",
    ]
