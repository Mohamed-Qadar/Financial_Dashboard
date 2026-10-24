"""Test helpers shared by all apps."""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, transaction

from apps.core.db_roles import app_role


@contextmanager
def as_app_role() -> Iterator[None]:
    """Run the enclosed database work as the restricted runtime role.

    Tests connect as the owner. This switches the current connection inside a savepoint; if
    the block raises, rolling back the savepoint also undoes the role switch.

    Limitation: PostgreSQL checks SET ROLE against the *session* user (the owner here), so
    code inside the block could switch back. Use it to test data access (privileges, RLS),
    not privilege escalation; escalation tests must log in as the app role
    (see apps/core/tests/test_db_roles.py).
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f'SET LOCAL ROLE "{app_role()}"')
        yield
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
