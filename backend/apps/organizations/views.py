"""Company endpoints (milestone 2.3a) and business registration (milestone 2.3b).

``GET companies/`` lists what the user may open (user stage, across tenants). The company
views are company-scoped (``CompanyScopedAPIView``): the active company comes from the
``X-Company-ID`` header and is verified on every request. ``POST auth/register/`` creates a
new business; it needs no session and no company.
"""

import logging

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import DatabaseError, transaction
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as account_services
from apps.accounts import throttling
from apps.accounts.models import normalize_email_address
from apps.audit.events import AuditEvent, Outcome
from apps.audit.services import record_event, record_failure_event
from apps.core import tenancy
from apps.core.client_ip import client_ip
from apps.core.exceptions import ServiceUnavailable
from apps.organizations import selectors, services
from apps.organizations.access import COMPANY_HEADER_PARAMETER, CompanyScopedAPIView
from apps.organizations.serializers import CompanySerializer, RegistrationSerializer

logger = logging.getLogger(__name__)


class RegistrationClosed(exceptions.APIException):
    status_code = 403
    default_detail = _("Registration of new businesses is closed.")
    default_code = "registration_closed"


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    """Registers a new business and its owner (decision D3, ``REGISTRATION_OPEN``).

    Answers 202 for every valid request, whether or not the e-mail already has an account, so
    the endpoint cannot be used to find out which addresses are registered. The new owner then
    signs in through ``auth/login/``. CSRF is enforced although no session is needed, like
    login: otherwise another site could register businesses in a visitor's browser.
    """

    permission_classes = [AllowAny]

    @extend_schema(request=RegistrationSerializer, responses={202: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        if not settings.REGISTRATION_OPEN:
            raise RegistrationClosed()
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        email = normalize_email_address(data["email"])
        throttling.enforce(
            request,
            [
                (throttling.REGISTER_PER_IP, client_ip(request) or "unknown"),
                (throttling.REGISTER_PER_EMAIL, email),
            ],
            AuditEvent.REGISTRATION_THROTTLED,
        )

        try:
            with transaction.atomic(durable=True):
                services.register_business(
                    email=email,
                    password=data["password"],
                    full_name=data["full_name"],
                    business_name=data["business_name"],
                    language=data["language"],
                    request=request,
                )
        except services.EmailAlreadyRegistered:
            self._existing_account(request, email, data["password"])
        except DatabaseError:
            record_failure_event(
                AuditEvent.REGISTRATION_FAILED,
                request=request,
                metadata={"reason": "storage_unavailable"},
            )
            raise ServiceUnavailable() from None
        return Response(status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _existing_account(request: Request, email: str, password: str) -> None:
        # Same hashing cost as a real registration, so response time does not tell the cases
        # apart. (A slow mail server would; see docs/SECURITY.md § 3.4.)
        make_password(password)
        record_failure_event(
            AuditEvent.REGISTRATION_FAILED,
            request=request,
            metadata={"reason": "email_taken"},
            target_type="user",
            target_id=account_services.find_user_id(email) or "",
        )
        try:
            account_services.send_registration_notice_email(email)
        except Exception:
            logger.exception("registration notice e-mail could not be sent")


class CompanyListView(APIView):
    """Companies the user can select. Not company-scoped: no X-Company-ID needed."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: CompanySerializer(many=True)}, tags=["companies"])
    def get(self, request: Request) -> Response:
        with transaction.atomic(durable=True), tenancy.user_context(request.user.pk):
            data = CompanySerializer(selectors.companies_for_user(request.user), many=True).data
        return Response(data)


class ActiveCompanyView(CompanyScopedAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[COMPANY_HEADER_PARAMETER],
        responses={200: CompanySerializer},
        tags=["companies"],
    )
    def get(self, request: Request) -> Response:
        return Response(CompanySerializer(request.company).data)


class CompanySelectView(CompanyScopedAPIView):
    """Records that the user switched to this company (the UI calls it from the picker).

    Authorization does not depend on it: every company-scoped request is checked on its own.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        parameters=[COMPANY_HEADER_PARAMETER],
        responses={200: CompanySerializer},
        tags=["companies"],
    )
    def post(self, request: Request) -> Response:
        company = request.company
        try:
            # Savepoint: a failed audit write leaves the request transaction usable, so the
            # 503 below is rendered normally and then everything rolls back.
            with transaction.atomic():
                record_event(
                    AuditEvent.COMPANY_SELECTED,
                    Outcome.SUCCESS,
                    request=request,
                    target_type="company",
                    target_id=company.pk,
                )
        except DatabaseError:
            self.defer_failure_event(
                AuditEvent.COMPANY_SELECTED,
                target_type="company",
                target_id=company.pk,
                metadata={"reason": "storage_unavailable"},
            )
            raise ServiceUnavailable() from None
        return Response(CompanySerializer(company).data)
