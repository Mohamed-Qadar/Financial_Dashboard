"""Active-company resolution for company-scoped API views (docs/SECURITY.md § 2).

The client names the active company in the ``X-Company-ID`` header on every request. The
header is a selector, not a credential: the server checks the user's membership and the
tenant/company status on every request and stores nothing about the choice in the session.
"""

import logging
import re
import uuid

from django.db import DatabaseError, transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import exceptions
from rest_framework.exceptions import Throttled
from rest_framework.views import APIView

from apps.accounts.throttling import enforce
from apps.audit.events import AuditEvent, Outcome
from apps.audit.services import record_failure_event
from apps.core import tenancy
from apps.core.rate_limit import RateLimit
from apps.organizations import selectors

logger = logging.getLogger(__name__)

COMPANY_HEADER = "X-Company-ID"
_UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

# Only denied attempts count, keyed by the user: a user probing company ids slows down only
# themselves, and legitimate requests never touch the counter.
COMPANY_ACCESS_DENIED_PER_USER = RateLimit("company_denied_user_min", limit=30, window_seconds=60)

COMPANY_HEADER_PARAMETER = OpenApiParameter(
    COMPANY_HEADER,
    OpenApiTypes.UUID,
    OpenApiParameter.HEADER,
    required=True,
    description="Id of the active company. Checked against the user's membership on every request.",
)


class CompanyRequired(exceptions.APIException):
    status_code = 400
    default_detail = _("Send the id of the active company in the X-Company-ID header.")
    default_code = "company_required"


def company_id_from_header(request) -> uuid.UUID:
    """The header's company id. Missing or not exactly one canonical UUID → 400."""
    value = request.headers.get(COMPANY_HEADER)
    if value is None or len(value) != 36 or not _UUID_PATTERN.fullmatch(value):
        raise CompanyRequired()
    return uuid.UUID(value)


class CompanyScopedAPIView(APIView):
    """Base class for every view that works inside one company.

    Request lifecycle:
    1. The whole view runs in one outermost transaction (``atomic(durable=True)``; there is
       no request-wide ATOMIC_REQUESTS), as the runtime database role.
    2. After authentication and permission checks: header → user stage → access check →
       tenant stage. Unknown company, another tenant's company, disabled membership and
       inactive tenant/company all answer the same 404.
    3. Any response with status >= 400 rolls the transaction back; a successful one clears
       the database context before committing.
    4. After the transaction: deferred FAILURE/DENIED audit events and, for a denied
       company, the per-user limit and its audit event.

    Views get ``request.tenant``, ``request.company`` and ``request.membership`` and pass
    them explicitly to selectors and services.
    """

    def dispatch(self, request, *args, **kwargs):
        self._deferred_failure_events: list[tuple[AuditEvent, dict]] = []
        self._denied_company_id: uuid.UUID | None = None
        with transaction.atomic(durable=True):
            tenancy.restrict_to_app_role()
            response = super().dispatch(request, *args, **kwargs)
            if response.status_code >= 400:
                transaction.set_rollback(True)
            else:
                tenancy.clear()
        return self._after_transaction(response)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Company data always needs a user, even if a subclass loosens permission_classes.
        if not request.user.is_authenticated:
            raise exceptions.NotAuthenticated()
        company_id = company_id_from_header(request)
        tenancy.set_user_stage(request.user.pk)
        access = selectors.company_access(request.user, company_id)
        if access is None:
            self._denied_company_id = company_id
            raise exceptions.NotFound()
        tenancy.set_tenant_stage(access.tenant.pk)
        request.tenant = access.tenant
        request.company = access.company
        request.membership = access.membership

    def defer_failure_event(self, event: AuditEvent, outcome=Outcome.FAILURE, **kwargs) -> None:
        """Record a FAILURE/DENIED event once this request's transaction has rolled back."""
        self._deferred_failure_events.append((event, {"outcome": outcome, **kwargs}))

    def _after_transaction(self, response):
        for event, kwargs in self._deferred_failure_events:
            record_failure_event(event, request=self.request, **kwargs)
        if self._denied_company_id is not None:
            response = self._handle_denied_company(response)
        return response

    def _handle_denied_company(self, response):
        request = self.request
        try:
            enforce(
                request,
                [(COMPANY_ACCESS_DENIED_PER_USER, str(request.user.pk))],
                AuditEvent.COMPANY_ACCESS_THROTTLED,
            )
        except Throttled as exc:
            return self.finalize_response(request, self.handle_exception(exc))
        except DatabaseError as exc:
            # Access stays denied; only the counting failed. No database error text in logs.
            logger.error(
                "denied company access could not be counted",
                extra={"error_type": type(exc).__name__},
            )
        record_failure_event(
            AuditEvent.COMPANY_ACCESS_DENIED,
            Outcome.DENIED,
            request=request,
            target_type="company",
            target_id=self._denied_company_id,
            metadata={"reason": "not_accessible"},
        )
        return response
