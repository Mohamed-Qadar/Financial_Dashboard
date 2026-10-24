"""Project-wide rules that should fail loudly when broken."""

import re
from io import StringIO
from pathlib import Path

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import models
from django.urls import URLResolver, get_resolver

BACKEND = Path(__file__).resolve().parent.parent


def _project_models():
    return [m for m in apps.get_models() if m.__module__.startswith("apps.")]


def test_no_float_fields_in_project_models():
    """Money and quantities must use DecimalField, never binary floating point."""
    offenders = [
        f"{model.__name__}.{field.name}"
        for model in _project_models()
        for field in model._meta.get_fields()
        if isinstance(field, models.FloatField)
    ]
    assert offenders == []


@pytest.mark.django_db
def test_migrations_are_up_to_date():
    output = StringIO()
    try:
        call_command("makemigrations", "--check", "--dry-run", stdout=output)
    except SystemExit as exc:  # raised when model changes have no migration
        pytest.fail(f"Missing migrations:\n{output.getvalue()} (exit {exc.code})")


# Modules allowed to change database roles or row-level security settings. Everything else
# must go through apps.core.tenancy, which only uses transaction-local settings.
DB_CONTEXT_MODULES = {"apps/core/tenancy.py", "apps/core/testing.py"}
DB_CONTEXT_PATTERN = re.compile(
    r"set_config\s*\(|\bSET\s+(LOCAL\s+|SESSION\s+)?(ROLE|app\.)|RESET\s+ROLE", re.I
)


def test_database_context_is_only_changed_by_the_tenancy_module():
    offenders = []
    for path in sorted(BACKEND.joinpath("apps").rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        if "/tests/" in relative or "/migrations/" in relative or relative in DB_CONTEXT_MODULES:
            continue
        if DB_CONTEXT_PATTERN.search(path.read_text(encoding="utf-8")):
            offenders.append(relative)
    assert offenders == []


# Project API views that deliberately work without an active company. Every other view must
# be company-scoped, so tenant data is never served without the membership check.
NOT_COMPANY_SCOPED = {
    "apps.accounts.views.CsrfView",
    "apps.accounts.views.LoginView",
    "apps.accounts.views.LogoutView",
    "apps.accounts.views.MeView",
    "apps.accounts.views.PasswordChangeView",
    "apps.accounts.views.PasswordResetRequestView",
    "apps.accounts.views.PasswordResetConfirmView",
    "apps.core.views.LivenessView",
    "apps.core.views.ReadinessView",
    "apps.organizations.views.CompanyListView",
}


def _url_view_classes(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _url_view_classes(pattern.url_patterns)
        else:
            view_class = getattr(pattern.callback, "view_class", None) or getattr(
                pattern.callback, "cls", None
            )
            if view_class is not None:
                yield view_class


def test_every_project_view_is_company_scoped_or_explicitly_exempt():
    from apps.organizations.access import CompanyScopedAPIView

    views = {
        f"{cls.__module__}.{cls.__qualname__}": cls
        for cls in _url_view_classes(get_resolver().url_patterns)
        if cls.__module__.startswith("apps.")
    }
    unscoped = sorted(
        name
        for name, cls in views.items()
        if not issubclass(cls, CompanyScopedAPIView) and name not in NOT_COMPANY_SCOPED
    )
    assert unscoped == []
    assert set(views) >= NOT_COMPANY_SCOPED  # the exemption list has no stale entries
