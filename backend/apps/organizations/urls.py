from django.urls import path

from apps.organizations import views

urlpatterns = [
    # Served under /api/v1/auth/ with the other account endpoints; lives here because it
    # creates a tenant, company and branch (apps.accounts must not depend on this app).
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("companies/", views.CompanyListView.as_view(), name="company-list"),
    path("company/", views.ActiveCompanyView.as_view(), name="company-active"),
    path("company/select/", views.CompanySelectView.as_view(), name="company-select"),
]
