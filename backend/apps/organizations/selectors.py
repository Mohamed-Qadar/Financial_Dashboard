"""Read queries for companies.

Every filter that decides access is written out here, in addition to row-level security,
so a missing or wrong policy is never the only check (docs/SECURITY.md § 2).
"""

import uuid
from dataclasses import dataclass

from django.db.models import Exists, OuterRef, QuerySet

from apps.organizations.models import Company
from apps.tenants.models import Membership, Tenant


@dataclass(frozen=True)
class CompanyAccess:
    tenant: Tenant
    company: Company
    membership: Membership


def _active_membership(user) -> QuerySet[Membership]:
    return Membership.objects.filter(
        tenant_id=OuterRef("tenant_id"), user_id=user.pk, status=Membership.Status.ACTIVE
    )


def companies_for_user(user) -> QuerySet[Company]:
    """Active companies of active tenants in which ``user`` has an active membership.

    Runs in the user stage (``tenancy.user_context``), across the user's tenants.
    """
    return (
        Company.objects.filter(is_active=True, tenant__status=Tenant.Status.ACTIVE)
        .filter(Exists(_active_membership(user)))
        .select_related("tenant", "base_currency")
        .order_by("tenant__name", "code", "id")
    )


def company_access(user, company_id: uuid.UUID) -> CompanyAccess | None:
    """The user's access to one company, or None (unknown, other tenant, or not allowed).

    Runs in the user stage. In milestone 2.3 an active membership grants every active
    company of an active tenant; roles narrow this in 2.4.
    """
    if not (user.is_authenticated and user.is_active):
        return None
    company = companies_for_user(user).filter(pk=company_id).first()
    if company is None:
        return None
    membership = Membership.objects.filter(
        tenant_id=company.tenant_id, user_id=user.pk, status=Membership.Status.ACTIVE
    ).first()
    if membership is None:
        return None
    return CompanyAccess(tenant=company.tenant, company=company, membership=membership)
