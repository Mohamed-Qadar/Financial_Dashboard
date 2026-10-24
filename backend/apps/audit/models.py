"""Append-only audit log.

Rows are written through apps.audit.services.record_event(). They are never updated or
deleted: the ORM refuses it here, the runtime database role has no UPDATE/DELETE/TRUNCATE
privilege, and a trigger rejects UPDATE/DELETE for every role (see docs/SECURITY.md for what
an owner or superuser can still do).
"""

from django.db import models
from django.db.models.functions import Now

from apps.audit.events import ActorType, Outcome


class ImmutableAuditLogError(Exception):
    pass


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableAuditLogError("Audit log entries cannot be updated.")

    def delete(self):
        raise ImmutableAuditLogError("Audit log entries cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableAuditLogError("Audit log entries cannot be updated.")


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    # Database clock, so the application cannot back-date entries.
    occurred_at = models.DateTimeField(db_default=Now(), editable=False)
    event_type = models.CharField(max_length=100)
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    actor_type = models.CharField(max_length=10, choices=ActorType.choices)
    # Plain UUIDs, not foreign keys: an audit row must outlive (and never cascade from) the
    # user, tenant or company it mentions. Tenant/company tables arrive in milestone 2.3.
    actor_id = models.UUIDField(null=True, blank=True)
    tenant_id = models.UUIDField(null=True, blank=True)
    company_id = models.UUIDField(null=True, blank=True)
    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    request_id = models.UUIDField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        db_table = "audit_logs"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(outcome__in=Outcome.values),
                name="audit_logs_outcome_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(actor_type__in=ActorType.values),
                name="audit_logs_actor_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(actor_type=ActorType.USER, actor_id__isnull=False)
                    | (~models.Q(actor_type=ActorType.USER) & models.Q(actor_id__isnull=True))
                ),
                name="audit_logs_actor_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=["occurred_at"], name="audit_logs_occurred_idx"),
            models.Index(fields=["event_type", "occurred_at"], name="audit_logs_event_idx"),
            models.Index(fields=["actor_id", "occurred_at"], name="audit_logs_actor_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.outcome} #{self.pk}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableAuditLogError("Audit log entries cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableAuditLogError("Audit log entries cannot be deleted.")
