"""Catalog of audit event types.

Only events that the system can actually emit are listed. Each milestone adds the events it
introduces (e.g. authentication events in 2.2, role changes in 2.4). Names are stable
identifiers: never rename or reuse one, because stored rows refer to them.
"""

from django.db import models


class AuditEvent(models.TextChoices):
    DB_RUNTIME_ROLE_ENSURED = (
        "security.db_runtime_role_ensured",
        "Runtime database role created or updated",
    )


class Outcome(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    DENIED = "denied", "Denied"


class ActorType(models.TextChoices):
    USER = "user", "User"
    SYSTEM = "system", "System"
    ANONYMOUS = "anonymous", "Anonymous"
