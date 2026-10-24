"""Project-wide rules that should fail loudly when broken."""

from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import models


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
