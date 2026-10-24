"""Setting up and cleaning up the row-level security context (apps.core.tenancy).

Runs on the owner test connection; ``tenancy`` switches it to the runtime role (a test aid,
not a boundary). Escalation and policy tests with a real runtime-role login live in
apps/organizations/tests/test_rls_app_role.py.
"""

import uuid

import pytest
from django.conf import settings
from django.db import connection, transaction

from apps.core import tenancy

OWNER = settings.DATABASES["default"]["USER"]
APP = settings.DATABASE_APP_ROLE
TENANT, USER = uuid.uuid4(), uuid.uuid4()

pytestmark = pytest.mark.django_db


def test_tenant_context_is_set_inside_and_cleared_after():
    with transaction.atomic():
        with tenancy.tenant_context(TENANT):
            assert tenancy.current() == (str(TENANT), "", APP)
        assert tenancy.current() == ("", "", OWNER)


def test_user_context_sets_only_the_user():
    with transaction.atomic():
        with tenancy.user_context(USER):
            assert tenancy.current() == ("", str(USER), APP)
        assert tenancy.current() == ("", "", OWNER)


def test_stages_replace_each_other_and_are_never_combined():
    with transaction.atomic():
        tenancy.restrict_to_app_role()
        tenancy.set_user_stage(USER)
        tenancy.set_tenant_stage(TENANT)
        assert tenancy.current()[:2] == (str(TENANT), "")
        tenancy.set_user_stage(USER)
        assert tenancy.current()[:2] == ("", str(USER))
        tenancy.clear()


def test_error_inside_a_context_is_undone_even_if_the_caller_continues():
    """A transaction-local setting survives RELEASE SAVEPOINT, but ROLLBACK TO undoes it."""
    with transaction.atomic():
        with pytest.raises(ValueError), tenancy.tenant_context(TENANT):
            raise ValueError("boom")
        assert tenancy.current() == ("", "", OWNER)


def test_role_switch_is_skipped_when_already_connected_as_the_runtime_role(monkeypatch):
    monkeypatch.setitem(connection.settings_dict, "USER", APP)
    with transaction.atomic(), tenancy.tenant_context(TENANT):
        # No SET ROLE was issued: the session still runs as the owner in this test.
        assert tenancy.current() == (str(TENANT), "", OWNER)


@pytest.mark.parametrize("value", ["not-a-uuid", "1; DROP TABLE users"])
def test_only_uuids_are_accepted(value):
    with pytest.raises(ValueError), transaction.atomic():
        tenancy.restrict_to_app_role()
        tenancy.set_tenant_stage(value)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "call",
    [
        lambda: tenancy.restrict_to_app_role(),
        lambda: tenancy.set_user_stage(USER),
        lambda: tenancy.set_tenant_stage(TENANT),
        lambda: tenancy.clear(),
    ],
)
def test_context_cannot_be_set_outside_a_transaction(call):
    """In autocommit mode the setting would apply to a single statement and mislead."""
    with pytest.raises(RuntimeError, match=r"transaction\.atomic"):
        call()


@pytest.mark.django_db(transaction=True)
def test_context_does_not_survive_the_end_of_a_real_transaction():
    with transaction.atomic():
        tenancy.restrict_to_app_role()
        tenancy.set_tenant_stage(TENANT)
        # No clear(): COMMIT alone must end the context.

    with transaction.atomic():
        assert tenancy.current() == ("", "", OWNER)
