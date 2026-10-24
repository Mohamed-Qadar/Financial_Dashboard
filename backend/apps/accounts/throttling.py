"""Rate limits for authentication endpoints (docs/SECURITY.md § 3).

Lockout resistance: per-account limits are keyed by account *and* client IP, so attempts
from one address cannot block the account owner elsewhere. A higher account-wide cap limits
distributed guessing; checks run in order and stop at the first exceeded limit, so attempts
already rejected per IP never count against the account-wide cap. Reaching that cap needs
at least five source addresses within one hour (residual, documented risk).
"""

from rest_framework.exceptions import Throttled

from apps.audit.events import AuditEvent, Outcome
from apps.audit.services import record_failure_event
from apps.core.rate_limit import RateLimit, hit

LOGIN_PER_IP = RateLimit("login_ip_min", limit=30, window_seconds=60)
LOGIN_PER_ACCOUNT_AND_IP_MINUTE = RateLimit("login_account_ip_min", limit=5, window_seconds=60)
LOGIN_PER_ACCOUNT_AND_IP_HOUR = RateLimit("login_account_ip_hour", limit=20, window_seconds=3600)
LOGIN_PER_ACCOUNT = RateLimit("login_account_hour", limit=100, window_seconds=3600)

PASSWORD_CHANGE_PER_USER_MINUTE = RateLimit("password_change_min", limit=5, window_seconds=60)
PASSWORD_CHANGE_PER_USER_HOUR = RateLimit("password_change_hour", limit=20, window_seconds=3600)

RESET_REQUEST_PER_IP = RateLimit("reset_request_ip_hour", limit=5, window_seconds=3600)
RESET_REQUEST_PER_EMAIL = RateLimit("reset_request_email_hour", limit=3, window_seconds=3600)
RESET_CONFIRM_PER_IP = RateLimit("reset_confirm_ip_hour", limit=20, window_seconds=3600)


def enforce(request, checks: list[tuple[RateLimit, str]], event: AuditEvent) -> None:
    """Count the attempt against each limit in order; raise Throttled at the first excess.

    The DENIED audit event is written once per window (on the first rejected attempt), so
    an attacker cannot flood the audit log through throttled requests.
    """
    for rule, identifier in checks:
        result = hit(rule, identifier)
        if not result.allowed:
            if result.first_exceeded:
                record_failure_event(
                    event, Outcome.DENIED, request=request, metadata={"limit": rule.scope}
                )
            raise Throttled(wait=result.retry_after)
