"""Test data for tenancy tests, created on the owner connection (row-level security bypassed).

``build_world()`` creates the tenants used by the isolation tests:

| Tenant | Status | Companies | Members |
|---|---|---|---|
| A | active | A1 (active, branch A1-HQ), A2 (inactive) | alice, carol (active) |
| B | active | B1 (active, branch B1-HQ) | bob, carol (active) |
| C | active | C1 | alice (**disabled**) |
| S | suspended | S1 | alice (active) |
"""

import time
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.finance.models import Currency
from apps.organizations.models import Branch, Company
from apps.tenants.models import Membership, Tenant


def usd() -> Currency:
    # Transactional tests flush tables, including the seeded currencies.
    currency, _ = Currency.objects.get_or_create(
        code="USD", defaults={"name": "US Dollar", "symbol": "$", "minor_units": 2}
    )
    return currency


def make_user(email: str):
    return get_user_model().objects.create_user(email)  # unusable password


def make_tenant(name: str, status=Tenant.Status.ACTIVE) -> Tenant:
    return Tenant.objects.create(name=name, status=status)


def make_company(tenant: Tenant, code: str, *, is_active: bool = True) -> Company:
    return Company.objects.create(
        tenant=tenant,
        code=code,
        legal_name=f"{code} Trading Ltd",
        base_currency=usd(),
        is_active=is_active,
    )


def make_branch(company: Company, code: str = "HQ") -> Branch:
    return Branch.objects.create(
        tenant_id=company.tenant_id, company=company, code=code, name=f"{company.code} {code}"
    )


def make_membership(tenant: Tenant, user, status=Membership.Status.ACTIVE) -> Membership:
    return Membership.objects.create(tenant=tenant, user=user, status=status)


@dataclass
class World:
    tenant_a: Tenant
    tenant_b: Tenant
    tenant_c: Tenant
    tenant_s: Tenant
    company_a1: Company
    company_a2: Company
    company_b1: Company
    company_c1: Company
    company_s1: Company
    branch_a1: Branch
    branch_b1: Branch
    alice: object
    bob: object
    carol: object
    membership_alice_a: Membership
    membership_carol_b: Membership


def build_world() -> World:
    tenant_a, tenant_b = make_tenant("Tenant A"), make_tenant("Tenant B")
    tenant_c = make_tenant("Tenant C")
    tenant_s = make_tenant("Tenant S", status=Tenant.Status.SUSPENDED)
    company_a1, company_b1 = make_company(tenant_a, "A1"), make_company(tenant_b, "B1")
    alice, bob, carol = (
        make_user("alice@example.com"),
        make_user("bob@example.com"),
        make_user("carol@example.com"),
    )
    world = World(
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        tenant_c=tenant_c,
        tenant_s=tenant_s,
        company_a1=company_a1,
        company_a2=make_company(tenant_a, "A2", is_active=False),
        company_b1=company_b1,
        company_c1=make_company(tenant_c, "C1"),
        company_s1=make_company(tenant_s, "S1"),
        branch_a1=make_branch(company_a1),
        branch_b1=make_branch(company_b1),
        alice=alice,
        bob=bob,
        carol=carol,
        membership_alice_a=make_membership(tenant_a, alice),
        membership_carol_b=make_membership(tenant_b, carol),
    )
    make_membership(tenant_a, carol)
    make_membership(tenant_b, bob)
    make_membership(tenant_c, alice, status=Membership.Status.DISABLED)
    make_membership(tenant_s, alice)
    return world


def signed_in(user, **client_kwargs) -> APIClient:
    """A client with a valid session for ``user`` (without the cost of a password login)."""
    client = APIClient(**client_kwargs)
    client.force_login(user)
    session = client.session
    session[LOGIN_AT_SESSION_KEY] = int(time.time())
    session.save()
    return client
