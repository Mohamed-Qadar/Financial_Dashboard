"""Business operations for tenants, companies and branches.

``register_business()`` (milestone 2.3b) lives here rather than in ``apps.tenants``: it
creates companies and branches, and ``tenants`` sits below ``organizations`` in the module
dependency direction (docs/ARCHITECTURE.md § 2).
"""

import uuid
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.accounts.models import normalize_email_address
from apps.audit.events import AuditEvent, Outcome
from apps.audit.services import record_event
from apps.core import tenancy
from apps.finance.models import Currency
from apps.organizations.models import Branch, Company
from apps.tenants.models import Membership, Tenant

DEFAULT_BASE_CURRENCY = "USD"  # decision: USD is every company's default base currency
DEFAULT_COMPANY_CODE = "MAIN"
DEFAULT_BRANCH_CODE = "MAIN"
# Both unique indexes on users.email: the column's own and the case-insensitive one.
EMAIL_UNIQUE_CONSTRAINTS = {"users_email_key", "users_email_ci_unique"}


class EmailAlreadyRegistered(Exception):
    """The e-mail address belongs to an existing account; nothing was written."""


@dataclass(frozen=True)
class RegisteredBusiness:
    user: object
    tenant: Tenant
    membership: Membership
    company: Company
    branch: Branch


def _violated_constraint(exc: IntegrityError) -> str | None:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def register_business(
    *,
    email: str,
    password: str,
    full_name: str,
    business_name: str,
    language: str,
    request=None,
) -> RegisteredBusiness:
    """Create the owner's user, the tenant, the owner membership, the first company and its
    default branch, with their audit events, in one transaction.

    Runs in the new tenant's stage (``apps.core.tenancy``), so every row passes the same
    row-level security policies as later requests. Raises ``EmailAlreadyRegistered`` when
    the address is taken — found by the check below, or by the unique index when two
    registrations of one address race.
    """
    email = normalize_email_address(email)
    User = get_user_model()
    if User.objects.filter(email=email).exists():
        raise EmailAlreadyRegistered

    tenant_id = uuid.uuid4()
    try:
        with transaction.atomic(), tenancy.tenant_context(tenant_id):
            user = User.objects.create_user(
                email, password, full_name=full_name, preferred_language=language
            )
            tenant = Tenant.objects.create(
                id=tenant_id, name=business_name, default_language=language
            )
            membership = Membership.objects.create(
                tenant=tenant, user=user, status=Membership.Status.ACTIVE, is_owner=True
            )
            company = Company.objects.create(
                tenant=tenant,
                code=DEFAULT_COMPANY_CODE,
                legal_name=business_name,
                base_currency=Currency.objects.get(code=DEFAULT_BASE_CURRENCY),
            )
            branch = Branch.objects.create(
                tenant=tenant, company=company, code=DEFAULT_BRANCH_CODE, name=business_name
            )
            # TODO(M3.3, M3.5): call the core seeding hook registry here, inside this
            # transaction — default units of measure (M3.3) and the default chart of
            # accounts (M3.5). Not before: their tables do not exist yet. Warehouses are
            # Phase 5 and are not created at registration.

            record_event(
                AuditEvent.BUSINESS_REGISTERED,
                Outcome.SUCCESS,
                request=request,
                actor=user,
                tenant_id=tenant.pk,
                company_id=company.pk,
                target_type="tenant",
                target_id=tenant.pk,
                metadata={"company_id": company.pk, "branch_id": branch.pk},
            )
            record_event(
                AuditEvent.MEMBERSHIP_CREATED,
                Outcome.SUCCESS,
                request=request,
                actor=user,
                tenant_id=tenant.pk,
                target_type="membership",
                target_id=membership.pk,
                metadata={"user_id": user.pk, "is_owner": True},
            )
    except IntegrityError as exc:
        if _violated_constraint(exc) in EMAIL_UNIQUE_CONSTRAINTS:
            raise EmailAlreadyRegistered from None
        raise

    return RegisteredBusiness(
        user=user, tenant=tenant, membership=membership, company=company, branch=branch
    )
