"""Database context for row-level security (docs/SECURITY.md § 2).

RLS policies read two transaction-local settings through ``app_current_tenant_id()`` and
``app_current_user_id()`` (migration core.0003):

- **user stage** (``app.user_id`` only): the user sees their own active memberships and the
  tenants/companies those memberships belong to. Used to resolve the active company and to
  list the companies a user may open.
- **tenant stage** (``app.tenant_id`` only): every tenant-owned row of that one tenant.

The two are never set together. Both are set with ``set_config(..., true)``, so they end with
the transaction and cannot leak into the next request on a reused connection. They are also
cleared explicitly when a block succeeds, because a transaction-local setting outlives a
released savepoint (nested ``atomic()`` blocks, tests).

Not a boundary against arbitrary SQL: the runtime role can set these values itself. RLS stops
application bugs (a forgotten filter) from crossing tenants; it does not stop an attacker who
can already run SQL as the runtime role.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, transaction

from apps.core.db_roles import app_role

TENANT_SETTING = "app.tenant_id"
USER_SETTING = "app.user_id"


def _require_transaction() -> None:
    if not connection.in_atomic_block:
        raise RuntimeError("Database tenant context can only be set inside transaction.atomic().")


def _set(tenant_id: uuid.UUID | None, user_id: uuid.UUID | None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, true), set_config(%s, %s, true)",
            [
                TENANT_SETTING,
                str(uuid.UUID(str(tenant_id))) if tenant_id is not None else "",
                USER_SETTING,
                str(uuid.UUID(str(user_id))) if user_id is not None else "",
            ],
        )


def _switches_role() -> bool:
    # The web process already connects as the runtime role. Owner connections (tests,
    # management commands) switch to it so the same policies apply; this is a test aid, not
    # a security boundary (PostgreSQL lets the session user switch back).
    return connection.settings_dict["USER"] != app_role()


def restrict_to_app_role() -> None:
    """Run the rest of the transaction as the runtime role (no-op for the web process)."""
    _require_transaction()
    if _switches_role():
        with connection.cursor() as cursor:
            cursor.execute(f'SET LOCAL ROLE "{app_role()}"')


def set_user_stage(user_id: uuid.UUID) -> None:
    _require_transaction()
    _set(tenant_id=None, user_id=user_id)


def set_tenant_stage(tenant_id: uuid.UUID) -> None:
    _require_transaction()
    _set(tenant_id=tenant_id, user_id=None)


def clear() -> None:
    """Remove the context before a successful block ends (see module docstring)."""
    _require_transaction()
    _set(tenant_id=None, user_id=None)
    if _switches_role():
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


@contextmanager
def user_context(user_id: uuid.UUID) -> Iterator[None]:
    """User stage for the enclosed block, in its own savepoint.

    If the block raises, rolling back the savepoint also undoes the settings and the role
    switch, even when the caller catches the exception and continues its transaction.
    """
    with transaction.atomic():
        restrict_to_app_role()
        set_user_stage(user_id)
        yield
        clear()


@contextmanager
def tenant_context(tenant_id: uuid.UUID) -> Iterator[None]:
    """Tenant stage for the enclosed block, in its own savepoint (see ``user_context``)."""
    with transaction.atomic():
        restrict_to_app_role()
        set_tenant_stage(tenant_id)
        yield
        clear()


def current() -> tuple[str, str, str]:
    """(tenant setting, user setting, current_user) — for tests and diagnostics."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT coalesce(current_setting(%s, true), ''), "
            "coalesce(current_setting(%s, true), ''), current_user",
            [TENANT_SETTING, USER_SETTING],
        )
        return cursor.fetchone()
