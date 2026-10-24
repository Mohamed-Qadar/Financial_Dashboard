"""Database constraints, tested on the owner connection.

The owner is a superuser in local Docker and bypasses row-level security, so these tests show
what the schema itself guarantees even when RLS is not in the way: composite foreign keys keep
references inside one tenant (PostgreSQL foreign-key checks ignore RLS), and unique and check
constraints hold for every writer.
"""

import pytest
from django.db import IntegrityError, connection, transaction

from apps.finance.models import Currency
from apps.organizations.models import Branch, Company
from apps.organizations.tests.factories import (
    build_world,
    make_branch,
    make_company,
    make_membership,
    make_tenant,
    usd,
)
from apps.tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    return build_world()


def _violates(callable_, match: str) -> None:
    with pytest.raises(IntegrityError, match=match), transaction.atomic():
        callable_()


# --- composite foreign keys -----------------------------------------------------------------


def test_branch_cannot_reference_a_company_of_another_tenant(world):
    _violates(
        lambda: Branch.objects.create(
            tenant=world.tenant_a, company=world.company_b1, code="X", name="X"
        ),
        "branches_company_same_tenant_fk",
    )


def test_branch_cannot_be_moved_to_another_tenant(world):
    _violates(
        lambda: Branch.objects.filter(pk=world.branch_a1.pk).update(tenant=world.tenant_b),
        "branches_company_same_tenant_fk",
    )


def test_company_with_branches_cannot_change_tenant(world):
    _violates(
        lambda: Company.objects.filter(pk=world.company_a1.pk).update(tenant=world.tenant_b),
        "branches_company_same_tenant_fk",
    )


def test_company_with_branches_cannot_be_deleted_at_database_level(world):
    # Django's own foreign keys are deferred to commit; the composite key fails immediately.
    with (
        pytest.raises(IntegrityError, match="branches_company_same_tenant_fk"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM companies WHERE id = %s", [world.company_a1.pk])


# --- unique and check constraints -----------------------------------------------------------


def test_company_code_is_unique_per_tenant_only(world):
    _violates(lambda: make_company(world.tenant_a, "A1"), "companies_tenant_code")
    assert make_company(world.tenant_b, "A1").tenant == world.tenant_b


def test_branch_code_is_unique_per_company_only(world):
    _violates(lambda: make_branch(world.company_a1, "HQ"), "branches_company_code")
    assert make_branch(world.company_b1, "HQ2").company == world.company_b1


def test_one_membership_per_user_and_tenant(world):
    _violates(lambda: make_membership(world.tenant_a, world.alice), "memberships_tenant_user")


@pytest.mark.parametrize(
    ("factory", "constraint"),
    [
        (lambda t: Tenant.objects.create(name="x", status="deleted"), "tenants_status_valid"),
        (
            lambda t: Tenant.objects.create(name="x", default_language="tr"),
            "tenants_language_valid",
        ),
        (
            lambda t: Company.objects.create(
                tenant=t, code="M0", legal_name="x", base_currency=usd(), fiscal_year_start_month=0
            ),
            "companies_fiscal_month_range",
        ),
        (
            lambda t: Company.objects.create(
                tenant=t,
                code="M13",
                legal_name="x",
                base_currency=usd(),
                fiscal_year_start_month=13,
            ),
            "companies_fiscal_month_range",
        ),
        (
            lambda t: Company.objects.create(
                tenant=t, code="CC", legal_name="x", base_currency=usd(), country_code="so"
            ),
            "companies_country_code_iso",
        ),
        (
            lambda t: Currency.objects.create(code="usd", name="x", symbol="x", minor_units=2),
            "currencies_code_iso",
        ),
        (
            lambda t: Currency.objects.create(code="XXX", name="x", symbol="x", minor_units=5),
            "currencies_minor_units_range",
        ),
    ],
)
def test_check_constraints(factory, constraint):
    tenant = make_tenant("Checks")
    _violates(lambda: factory(tenant), constraint)


def test_membership_status_is_checked():
    tenant = make_tenant("Checks")
    user = Membership._meta.get_field("user").related_model.objects.create_user("x@example.com")
    _violates(
        lambda: Membership.objects.create(tenant=tenant, user=user, status="owner"),
        "memberships_status_valid",
    )


def test_seeded_currencies():
    assert {(c.code, c.minor_units) for c in Currency.objects.filter(code__in=["USD", "SOS"])} == {
        ("USD", 2),
        ("SOS", 2),
    }
