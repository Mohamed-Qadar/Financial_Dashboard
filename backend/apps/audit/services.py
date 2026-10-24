"""Writing audit events.

Transaction rule: record_event() writes on the caller's database connection, so the entry
commits or rolls back together with the operation it describes. A SUCCESS event therefore
must be recorded inside the operation's transaction (``transaction.atomic()``); recording one
in autocommit mode raises, because the event could outlive a failed operation. FAILURE and
DENIED events may be recorded outside a transaction (after the failed work rolled back).
"""

import ipaddress
import json
from typing import Any

from django.db import connection

from apps.audit.events import ActorType, AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.core.request_id import current_request_id

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


def _client_ip(request) -> str | None:
    # REMOTE_ADDR only. Behind the Next.js proxy this is the proxy's address; trusted
    # X-Forwarded-For handling is added with authentication (milestone 2.2).
    if request is None:
        return None
    try:
        return str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        return None


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
    return AuditLog.objects.create(
        event_type=event,
        outcome=outcome,
        actor_type=actor_type,
        actor_id=actor_id,
        tenant_id=tenant_id,
        company_id=company_id,
        target_type=target_type,
        target_id=str(target_id)[:MAX_TARGET_ID_LENGTH],
        request_id=getattr(request, "request_id", None) or current_request_id(),
        ip_address=_client_ip(request),
        metadata=clean_metadata,
    )
