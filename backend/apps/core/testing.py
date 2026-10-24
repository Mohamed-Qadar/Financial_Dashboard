"""Test helpers shared by all apps."""

from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO

import psycopg
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction

from apps.core.db_roles import app_role


@contextmanager
def as_app_role() -> Iterator[None]:
    """Run the enclosed database work as the restricted runtime role.

    Tests connect as the owner. This switches the current connection inside a savepoint; if
    the block raises, rolling back the savepoint also undoes the role switch.

    Limitation: PostgreSQL checks SET ROLE against the *session* user (the owner here), so
    code inside the block could switch back. Use it to test data access (privileges, RLS),
    not privilege escalation; escalation tests must use ``app_role_connection()``.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f'SET LOCAL ROLE "{app_role()}"')
        yield
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


@contextmanager
def app_role_connection() -> Iterator[psycopg.Connection]:
    """A separate connection that logs in as the runtime role, exactly like the web process.

    Needs ``@pytest.mark.django_db(transaction=True)``: it cannot see data from the test's
    uncommitted transaction. Autocommit is on, so a failed statement does not poison the next.
    """
    call_command("ensure_db_roles", stdout=StringIO(), stderr=StringIO())
    db = connection.settings_dict
    with psycopg.connect(
        host=db["HOST"],
        port=db["PORT"],
        dbname=db["NAME"],
        user=app_role(),
        password=settings.DATABASE_APP_PASSWORD,
        connect_timeout=5,
        autocommit=True,
    ) as conn:
        yield conn
