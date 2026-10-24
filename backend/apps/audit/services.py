"""Writing audit events.

Transaction rule: record_event() writes on the caller's database connection, so the entry
commits or rolls back together with the operation it describes. A SUCCESS event therefore
must be recorded inside the operation's transaction (``transaction.atomic()``); recording one
in autocommit mode raises, because the event could outlive a failed operation.

FAILURE and DENIED events are recorded with record_failure_event(), after the failed work has
rolled back, in their own outermost transaction. If that write fails, the event is written to
the application log at CRITICAL level instead of being dropped.

Row-level security (migration audit.0002): inside a tenant context an entry must carry that
tenant, so tenant and company default to ``request.tenant`` / ``request.company``. Entries are
inserted without ``RETURNING``: the runtime role may append platform entries (no tenant) but
never read them, and PostgreSQL applies read policies to rows returned by an INSERT.
"""

import json
import logging
from typing import Any

from django.db import DatabaseError, connection, transaction

from apps.audit.events import ActorType, AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.core import tenancy
from apps.core.client_ip import client_ip
from apps.core.request_id import current_request_id

logger = logging.getLogger("apps.audit")

REDACTED = "[redacted]"
# Metadata keys containing any of these fragments (case-insensitive) are never stored.
SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "session",
    "cookie",
    "authorization",
    "csrf",
    "api_key",
    "apikey",
    "private_key",
    "otp",
)
MAX_METADATA_BYTES = 4096
MAX_STRING_LENGTH = 500
MAX_TARGET_ID_LENGTH = 64

# The id comes from the table's identity sequence and the time from the database clock, so the
# entry can be returned complete without reading it back (see module docstring).
NEXT_ID_SQL = "SELECT nextval(pg_get_serial_sequence('audit_logs', 'id')), statement_timestamp()"
INSERT_SQL = """
    INSERT INTO audit_logs (
        id, occurred_at, event_type, outcome, actor_type, actor_id, tenant_id, company_id,
        target_type, target_id, request_id, ip_address, metadata
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s::inet, %s::jsonb)
"""


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def sanitize_metadata(value: Any) -> Any:
    """Redact sensitive keys, shorten long strings and make values JSON-safe."""
    if isinstance(value, dict):
        return {
            str(key): REDACTED if _is_sensitive(str(key)) else sanitize_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [sanitize_metadata(item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value)  # Decimal, UUID, datetime, ... become strings.
    if len(text) > MAX_STRING_LENGTH:
        return text[:MAX_STRING_LENGTH] + "…"
    return text


def _resolve_actor(request, actor, system: bool) -> tuple[str, Any]:
    if actor is not None:
        return ActorType.USER, actor.pk
    if system:
        return ActorType.SYSTEM, None
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return ActorType.USER, user.pk
    return ActorType.ANONYMOUS, None


def record_event(
    event: AuditEvent | str,
    outcome: Outcome | str,
    *,
    request=None,
    actor=None,
    system: bool = False,
    tenant_id=None,
    company_id=None,
    target_type: str = "",
    target_id: Any = "",
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one audit entry. See the module docstring for the transaction rule."""
    event = AuditEvent(event)  # ValueError for event types not in the catalog
    outcome = Outcome(outcome)
    if outcome == Outcome.SUCCESS and not connection.in_atomic_block:
        raise RuntimeError(
            "Record SUCCESS audit events inside the operation's transaction.atomic() block."
        )

    clean_metadata = sanitize_metadata(metadata or {})
    size = len(json.dumps(clean_metadata, ensure_ascii=False).encode())
    if size > MAX_METADATA_BYTES:
        raise ValueError(f"Audit metadata is {size} bytes; the limit is {MAX_METADATA_BYTES}.")

    actor_type, actor_id = _resolve_actor(request, actor, system)
    tenant_id, company_id = _resolve_tenant(request, tenant_id, company_id)
    entry = AuditLog(
        event_type=event,
        outcome=outcome,
        actor_type=actor_type,
        actor_id=actor_id,
        tenant_id=tenant_id,
        company_id=company_id,
        target_type=target_type,
        target_id=str(target_id)[:MAX_TARGET_ID_LENGTH],
        request_id=getattr(request, "request_id", None) or current_request_id(),
        ip_address=client_ip(request),
        metadata=clean_metadata,
    )
    _insert(entry)
    return entry


def _resolve_tenant(request, tenant_id, company_id) -> tuple[Any, Any]:
    """Explicit ids win; otherwise the request's active tenant and company (if any)."""
    if tenant_id is None and company_id is None:
        tenant = getattr(request, "tenant", None)
        company = getattr(request, "company", None)
        tenant_id = tenant.pk if tenant is not None else None
        company_id = company.pk if company is not None else None
    return tenant_id, company_id


def _insert(entry: AuditLog) -> None:
    with connection.cursor() as cursor:
        cursor.execute(NEXT_ID_SQL)
        entry.id, entry.occurred_at = cursor.fetchone()
        cursor.execute(
            INSERT_SQL,
            [
                entry.id,
                entry.occurred_at,
                entry.event_type,
                entry.outcome,
                entry.actor_type,
                entry.actor_id,
                entry.tenant_id,
                entry.company_id,
                entry.target_type,
                entry.target_id,
                entry.request_id,
                entry.ip_address,
                json.dumps(entry.metadata, ensure_ascii=False),
            ],
        )
    entry._state.adding = False
    entry._state.db = connection.alias


def record_failure_event(
    event: AuditEvent | str,
    outcome: Outcome | str = Outcome.FAILURE,
    **kwargs: Any,
) -> AuditLog | None:
    """Record a FAILURE/DENIED event after the failed operation's transaction rolled back.

    Runs in its own outermost transaction: calling it inside another transaction raises
    RuntimeError, because the event would be lost if that transaction rolled back. An event
    of a tenant (explicit or from ``request.tenant``) is written in that tenant's context,
    which the rolled-back request transaction no longer provides.

    If the database cannot store the event, it is logged at CRITICAL level and None is
    returned; the caller's response is unchanged. The log line carries the event type,
    outcome, request ID and the error's class and SQLSTATE only: no metadata, and not the
    database error text, which can quote the rejected row (IP address, metadata).
    """
    if Outcome(outcome) == Outcome.SUCCESS:
        raise ValueError("Use record_event() inside the operation's transaction for successes.")
    event, outcome = AuditEvent(event), Outcome(outcome)
    request = kwargs.get("request")
    kwargs["tenant_id"], kwargs["company_id"] = _resolve_tenant(
        request, kwargs.get("tenant_id"), kwargs.get("company_id")
    )
    try:
        with transaction.atomic(durable=True):
            if kwargs["tenant_id"] is None:
                return record_event(event, outcome, **kwargs)
            with tenancy.tenant_context(kwargs["tenant_id"]):
                return record_event(event, outcome, **kwargs)
    except DatabaseError as exc:
        logger.critical(
            "audit event could not be stored",
            extra={
                "audit_event": str(event),
                "audit_outcome": str(outcome),
                "audit_request_id": getattr(request, "request_id", None) or current_request_id(),
                "error_type": type(exc).__name__,
                "sqlstate": getattr(exc.__cause__, "sqlstate", None),
            },
        )
        return None
