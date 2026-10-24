"""URLs with test-only company-scoped views (``@pytest.mark.urls``)."""

from django.urls import include, path
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.organizations.access import CompanyScopedAPIView
from apps.organizations.models import Branch, Company


class CreateBranchView(CompanyScopedAPIView):
    """Writes a branch in the active company; ``?fail=1`` fails afterwards with a 400."""

    def post(self, request):
        branch = Branch.objects.create(
            tenant=request.tenant, company=request.company, code=request.data["code"], name="T"
        )
        if request.query_params.get("fail"):
            raise exceptions.ValidationError({"code": ["fails after the write"]})
        return Response({"id": str(branch.pk)}, status=201)


class CrossTenantWriteView(CompanyScopedAPIView):
    """A bug that writes into another tenant: row-level security must reject it."""

    def post(self, request):
        Branch.objects.create(
            tenant_id=request.data["tenant_id"],
            company_id=request.data["company_id"],
            code="EVIL",
            name="Evil",
        )
        return Response(status=201)


class ForgottenFilterView(CompanyScopedAPIView):
    """A bug that queries without a tenant filter: RLS still limits it to the active tenant."""

    def get(self, request):
        return Response(sorted(str(pk) for pk in Company.objects.values_list("pk", flat=True)))


class LoosePermissionsView(CompanyScopedAPIView):
    """Misconfigured subclass: company scoping must still require a signed-in user."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"company": str(request.company.pk)})


urlpatterns = [
    path("test/loose/", LoosePermissionsView.as_view(), name="test-loose-permissions"),
    path("api/v1/", include("apps.organizations.urls")),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("test/branches/", CreateBranchView.as_view(), name="test-create-branch"),
    path("test/cross-tenant/", CrossTenantWriteView.as_view(), name="test-cross-tenant"),
    path("test/forgotten-filter/", ForgottenFilterView.as_view(), name="test-forgotten-filter"),
]
