"""Tenants (business accounts) and memberships (docs/SECURITY.md § 2, decision D1).

A tenant owns companies; users join a tenant through a membership. Every tenant-owned table
inherits ``TenantOwnedModel`` and is protected by row-level security (``apps.core.rls``);
``tests/test_rls_catalog.py`` fails if one is not.
"""

import uuid

from django.conf import settings
from django.db import models

from apps.accounts.models import User


class TenantStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    CLOSED = "closed", "Closed"


class MembershipStatus(models.TextChoices):
    INVITED = "invited", "Invited"  # used by invitations (milestone 2.6)
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"


class Tenant(models.Model):
    Status = TenantStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    default_language = models.CharField(
        max_length=5, choices=User.Language.choices, default=User.Language.SOMALI
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=TenantStatus.values), name="tenants_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(default_language__in=User.Language.values),
                name="tenants_language_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TenantOwnedModel(models.Model):
    """Base for every row that belongs to one tenant.

    ``UNIQUE (tenant_id, id)`` lets children reference ``(tenant_id, <parent>_id)`` with a
    composite foreign key, so a row can never point at another tenant's row.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="%(class)s_tenant_id_unique"),
        ]


class Membership(TenantOwnedModel):
    """A user's membership in a tenant. Access is re-checked on every request."""

    Status = MembershipStatus

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    # At least one active owner per tenant (service rule from milestone 2.3b on).
    is_owner = models.BooleanField(default=False)

    class Meta(TenantOwnedModel.Meta):
        db_table = "memberships"
        constraints = [
            *TenantOwnedModel.Meta.constraints,
            models.UniqueConstraint(fields=["tenant", "user"], name="memberships_tenant_user"),
            models.CheckConstraint(
                condition=models.Q(status__in=MembershipStatus.values),
                name="memberships_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["user", "status"], name="memberships_user_status_idx")]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.tenant_id} ({self.status})"
