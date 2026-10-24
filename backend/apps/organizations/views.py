"""Company endpoints (milestone 2.3a).

``GET companies/`` lists what the user may open (user stage, across tenants). The other views
are company-scoped (``CompanyScopedAPIView``): the active company comes from the
``X-Company-ID`` header and is verified on every request.
"""

from django.db import DatabaseError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.events import AuditEvent, Outcome
from apps.audit.services import record_event
from apps.core import tenancy
from apps.core.exceptions import ServiceUnavailable
from apps.organizations import selectors
from apps.organizations.access import COMPANY_HEADER_PARAMETER, CompanyScopedAPIView
from apps.organizations.serializers import CompanySerializer


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
