from django.urls import path

from apps.organizations import views

urlpatterns = [
    path("companies/", views.CompanyListView.as_view(), name="company-list"),
    path("company/", views.ActiveCompanyView.as_view(), name="company-active"),
    path("company/select/", views.CompanySelectView.as_view(), name="company-select"),
]
