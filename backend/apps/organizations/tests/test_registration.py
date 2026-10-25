"""Business registration, ``POST /api/v1/auth/register/`` (milestone 2.3b).

Most tests run inside the test transaction. The rollback and database-isolation tests use
real transactions (``transaction=True``): the view's block is then the outermost
transaction, and the isolation checks log in as the runtime role like the web process.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

import psycopg
import pytest
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import DatabaseError, connection, transaction
from django.db.models.query import QuerySet
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts import throttling
from apps.audit.events import AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.core import tenancy
from apps.core.rate_limit import RateLimit
from apps.core.testing import app_role_connection
from apps.organizations.models import Branch, Company
from apps.organizations.tests.factories import make_user, usd
from apps.tenants.models import Membership, Tenant, TenantOwnedModel

PASSWORD = "Hodan-Store-2026!"
OWNER = settings.DATABASES["default"]["USER"]


def payload(**overrides) -> dict:
    data = {
        "email": "hodan@example.com",
        "password": PASSWORD,
        "full_name": "Hodan Ali",
        "business_name": "Hodan General Store",
    }
    data.update(overrides)
    return data


def register(client: APIClient | None = None, *, extra: dict | None = None, **overrides):
    client = client or APIClient()
    return client.post(
        reverse("auth-register"), payload(**overrides), format="json", **(extra or {})
    )


def tenant_table_counts() -> dict[str, int]:
    """Rows per tenant-owned table, read on the owner connection (no row-level security)."""
    counts = {"tenants": Tenant.objects.count()}
    for model in apps.get_models():
        if issubclass(model, TenantOwnedModel):
            counts[model._meta.db_table] = model.objects.count()
    return counts


def events(event_type) -> list[AuditLog]:
    return list(AuditLog.objects.filter(event_type=event_type).order_by("id"))


def sign_in(email: str, password: str = PASSWORD) -> APIClient:
    client = APIClient()
    response = client.post(
        reverse("auth-login"), {"email": email, "password": password}, format="json"
    )
    assert response.status_code == 200
    return client


# --- what one registration creates ----------------------------------------------------------


@pytest.mark.django_db
def test_registration_creates_owner_tenant_company_and_branch():
    response = register()

    assert response.status_code == 202
    assert response.content == b""
    user = get_user_model().objects.get(email="hodan@example.com")
    assert (user.full_name, user.preferred_language) == ("Hodan Ali", "so")
    assert user.check_password(PASSWORD)
    assert user.password.startswith("argon2")

    tenant = Tenant.objects.get()
    assert (tenant.name, tenant.status, tenant.default_language) == (
        "Hodan General Store",
        Tenant.Status.ACTIVE,
        "so",
    )
    membership = Membership.objects.get()
    assert (membership.tenant_id, membership.user_id) == (tenant.pk, user.pk)
    assert (membership.is_owner, membership.status) == (True, Membership.Status.ACTIVE)

    company = Company.objects.get()
    assert company.tenant_id == tenant.pk
    assert (company.code, company.legal_name, company.base_currency_id) == (
        "MAIN",
        "Hodan General Store",
        "USD",
    )
    assert (company.country_code, company.timezone, company.fiscal_year_start_month) == (
        "SO",
        "Africa/Mogadishu",
        1,
    )
    branch = Branch.objects.get()
    assert (branch.tenant_id, branch.company_id) == (tenant.pk, company.pk)
    assert (branch.code, branch.name, branch.is_active) == ("MAIN", "Hodan General Store", True)

    assert tenancy.current() == ("", "", OWNER)


@pytest.mark.django_db
def test_only_the_four_tenancy_tables_get_rows():
    """No warehouse (Phase 5) and no chart of accounts (M3.5) at registration."""
    register()

    counts = tenant_table_counts()
    assert {table: n for table, n in counts.items() if n} == {
        "tenants": 1,
        "memberships": 1,
        "companies": 1,
        "branches": 1,
    }


@pytest.mark.django_db
def test_language_choice_sets_tenant_and_user_language():
    assert register(language="en").status_code == 202

    assert Tenant.objects.get().default_language == "en"
    assert get_user_model().objects.get().preferred_language == "en"


@pytest.mark.django_db
def test_registered_owner_can_sign_in_and_open_the_company():
    register()
    company = Company.objects.get()

    client = sign_in("hodan@example.com")

    listed = client.get(reverse("company-list"))
    assert [c["id"] for c in listed.json()] == [str(company.pk)]
    active = client.get(reverse("company-active"), HTTP_X_COMPANY_ID=str(company.pk))
    assert active.status_code == 200
    assert active.json()["code"] == "MAIN"


@pytest.mark.django_db
def test_registration_is_audited_inside_the_new_tenant():
    register(extra={"REMOTE_ADDR": "203.0.113.7"})
    user = get_user_model().objects.get()
    tenant, company, branch = Tenant.objects.get(), Company.objects.get(), Branch.objects.get()
    membership = Membership.objects.get()

    [registered] = events(AuditEvent.BUSINESS_REGISTERED)
    assert registered.outcome == Outcome.SUCCESS
    assert (registered.actor_id, registered.tenant_id, registered.company_id) == (
        user.pk,
        tenant.pk,
        company.pk,
    )
    assert (registered.target_type, registered.target_id) == ("tenant", str(tenant.pk))
    assert registered.metadata == {"company_id": str(company.pk), "branch_id": str(branch.pk)}
    assert str(registered.ip_address) == "203.0.113.7"
    assert registered.request_id is not None

    [created] = events(AuditEvent.MEMBERSHIP_CREATED)
    assert (created.tenant_id, created.target_type, created.target_id) == (
        tenant.pk,
        "membership",
        str(membership.pk),
    )
    assert created.metadata == {"user_id": str(user.pk), "is_owner": True}
    stored = str(registered.metadata) + str(created.metadata)
    assert PASSWORD not in stored and "hodan@example.com" not in stored


# --- an e-mail that already has an account -------------------------------------------------


@pytest.mark.django_db
def test_taken_email_gets_the_same_answer_and_changes_nothing():
    existing = make_user("hodan@example.com")  # no usable password
    fresh = register(email="amina@example.com")
    mail.outbox.clear()

    taken = register(email="  HODAN@Example.com ")

    assert (taken.status_code, taken.content) == (fresh.status_code, fresh.content)
    assert Tenant.objects.count() == 1  # only Amina's business
    existing.refresh_from_db()
    assert not existing.has_usable_password()
    assert not Membership.objects.filter(user=existing).exists()
    [failed] = events(AuditEvent.REGISTRATION_FAILED)
    assert (failed.outcome, failed.metadata) == (Outcome.FAILURE, {"reason": "email_taken"})
    assert (failed.target_type, failed.target_id, failed.tenant_id) == (
        "user",
        str(existing.pk),
        None,
    )
    [notice] = mail.outbox
    assert notice.to == ["hodan@example.com"]
    assert "already has an account" in notice.body


@pytest.mark.django_db
def test_racing_registrations_of_one_email_are_treated_as_taken():
    """The pre-check misses an account created a moment earlier; the unique index catches it."""
    make_user("hodan@example.com")

    with mock.patch.object(QuerySet, "exists", return_value=False):
        response = register()

    assert response.status_code == 202
    assert tenant_table_counts()["tenants"] == 0
    [failed] = events(AuditEvent.REGISTRATION_FAILED)
    assert failed.metadata == {"reason": "email_taken"}
    assert tenancy.current() == ("", "", OWNER)


# --- rejected requests -----------------------------------------------------------------------


@pytest.mark.django_db
def test_closed_registration_is_refused(settings):
    settings.REGISTRATION_OPEN = False

    response = register()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_closed"
    assert get_user_model().objects.count() == 0
    assert tenant_table_counts()["tenants"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"password": "1234567890123"}, "password"),  # numeric only
        ({"password": "short1!"}, "password"),
        ({"password": "hodan@example.com"}, "password"),  # same as the e-mail
        ({"email": "not-an-email"}, "email"),
        ({"business_name": ""}, "business_name"),
        ({"full_name": ""}, "full_name"),
        ({"language": "fr"}, "language"),
    ],
)
def test_invalid_input_is_rejected_before_anything_is_written(overrides, field):
    response = register(**overrides)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in error["details"]
    assert get_user_model().objects.count() == 0
    assert tenant_table_counts()["tenants"] == 0


@pytest.mark.django_db
def test_registration_needs_the_csrf_token():
    strict = APIClient(enforce_csrf_checks=True)

    refused = register(strict)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "csrf_failed"

    strict.get(reverse("auth-csrf"))
    token = strict.cookies["csrftoken"].value
    accepted = register(strict, extra={"HTTP_X_CSRFTOKEN": token})
    assert accepted.status_code == 202


@pytest.mark.django_db
def test_registration_is_rate_limited_per_email(pinned_rate_limit_clock):
    assert throttling.REGISTER_PER_EMAIL.limit == 3
    for _ in range(3):
        assert register().status_code == 202  # one registration, then "taken" answers

    response = register()

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
    assert Tenant.objects.count() == 1
    [throttled] = events(AuditEvent.REGISTRATION_THROTTLED)
    assert throttled.metadata == {"limit": "register_email_hour"}


@pytest.mark.django_db
def test_registration_is_rate_limited_per_ip(pinned_rate_limit_clock, monkeypatch):
    assert throttling.REGISTER_PER_IP.limit == 10
    # Two allowed attempts instead of ten keep the test fast (each one hashes a password).
    monkeypatch.setattr(
        throttling, "REGISTER_PER_IP", RateLimit("register_ip_hour", limit=2, window_seconds=3600)
    )
    same_ip = {"REMOTE_ADDR": "198.51.100.20"}
    assert register(email="a@example.com", extra=same_ip).status_code == 202
    assert register(email="b@example.com", extra=same_ip).status_code == 202

    assert register(email="c@example.com", extra=same_ip).status_code == 429
    other_ip = {"REMOTE_ADDR": "198.51.100.21"}
    assert register(email="c@example.com", extra=other_ip).status_code == 202


# --- isolation between registered businesses ------------------------------------------------


@pytest.mark.django_db
def test_second_registration_is_a_separate_tenant_that_cannot_see_the_first():
    register()
    register(email="bashir@example.com", full_name="Bashir Omar", business_name="Bashir Pharmacy")
    hodan_company = Company.objects.get(legal_name="Hodan General Store")
    bashir_company = Company.objects.get(legal_name="Bashir Pharmacy")
    assert hodan_company.tenant_id != bashir_company.tenant_id
    assert Membership.objects.filter(user__email="bashir@example.com").get().tenant_id == (
        bashir_company.tenant_id
    )

    bashir = sign_in("bashir@example.com")

    assert [c["id"] for c in bashir.get(reverse("company-list")).json()] == [str(bashir_company.pk)]
    foreign = {"HTTP_X_COMPANY_ID": str(hodan_company.pk)}
    assert bashir.get(reverse("company-active"), **foreign).status_code == 404
    assert bashir.post(reverse("company-select"), **foreign).status_code == 404


# --- real transactions: rollback ------------------------------------------------------------


def assert_nothing_registered() -> None:
    assert get_user_model().objects.count() == 0
    assert all(n == 0 for n in tenant_table_counts().values())
    assert events(AuditEvent.BUSINESS_REGISTERED) == []
    assert events(AuditEvent.MEMBERSHIP_CREATED) == []


def assert_connection_is_clean() -> None:
    assert not connection.in_atomic_block
    with transaction.atomic():
        assert tenancy.current() == ("", "", OWNER)


@pytest.mark.django_db(transaction=True)
def test_failure_after_the_company_insert_rolls_everything_back():
    usd()  # transactional tests flush the seeded currencies
    with mock.patch.object(Branch.objects, "create", side_effect=DatabaseError("insert failed")):
        response = register()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert_nothing_registered()
    [failed] = events(AuditEvent.REGISTRATION_FAILED)
    assert (failed.metadata, failed.tenant_id) == ({"reason": "storage_unavailable"}, None)
    assert_connection_is_clean()


@pytest.mark.django_db(transaction=True)
def test_registration_fails_closed_when_its_audit_event_cannot_be_written():
    usd()
    with mock.patch(
        "apps.organizations.services.record_event", side_effect=DatabaseError("audit failed")
    ):
        response = register()

    assert response.status_code == 503
    assert_nothing_registered()
    assert_connection_is_clean()


@pytest.mark.django_db(transaction=True)
def test_successful_registration_is_committed_with_its_events():
    usd()

    assert register().status_code == 202

    assert_connection_is_clean()
    assert {table: n for table, n in tenant_table_counts().items() if n} == {
        "tenants": 1,
        "memberships": 1,
        "companies": 1,
        "branches": 1,
    }
    assert len(events(AuditEvent.BUSINESS_REGISTERED)) == 1


# --- real transactions: row-level security as the runtime role ------------------------------

TENANCY_TABLES = ("tenants", "memberships", "companies", "branches")


@contextmanager
def stage(conn, *, tenant=None, user=None) -> Iterator[psycopg.Cursor]:
    """One transaction in the given stage (like apps.core.tenancy), always rolled back."""
    with conn.transaction(force_rollback=True), conn.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true), set_config('app.user_id', %s, true)",
            [str(tenant or ""), str(user or "")],
        )
        yield cursor


def tenant_ids(cursor, table: str) -> set:
    column = "id" if table == "tenants" else "tenant_id"
    cursor.execute(f"SELECT {column} FROM {table}")  # noqa: S608 - fixed table names
    return {row[0] for row in cursor.fetchall()}


@pytest.mark.django_db(transaction=True)
def test_registered_businesses_are_isolated_by_row_level_security():
    usd()
    register()
    register(email="bashir@example.com", full_name="Bashir Omar", business_name="Bashir Pharmacy")
    hodan = Membership.objects.get(user__email="hodan@example.com")
    bashir = Membership.objects.get(user__email="bashir@example.com")

    with app_role_connection() as conn:
        for own, other in ((hodan, bashir), (bashir, hodan)):
            with stage(conn, tenant=own.tenant_id) as cursor:
                for table in TENANCY_TABLES:
                    assert tenant_ids(cursor, table) == {own.tenant_id}, table
                cursor.execute("SELECT DISTINCT tenant_id FROM audit_logs")
                assert {row[0] for row in cursor.fetchall()} == {own.tenant_id}
            # Writing into the other tenant from this tenant's stage is refused.
            with (
                stage(conn, tenant=own.tenant_id) as cursor,
                pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"),
            ):
                cursor.execute(
                    "INSERT INTO branches (id, tenant_id, company_id, code, name, address, "
                    "phone, is_active, created_at, updated_at) SELECT gen_random_uuid(), "
                    "%s, id, 'X', 'X', '', '', true, now(), now() FROM companies LIMIT 1",
                    [str(other.tenant_id)],
                )

        with stage(conn) as cursor:  # no context: nothing at all
            for table in TENANCY_TABLES:
                assert tenant_ids(cursor, table) == set(), table

        with stage(conn, user=hodan.user_id) as cursor:  # user stage: only own business
            assert tenant_ids(cursor, "companies") == {hodan.tenant_id}
