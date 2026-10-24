import os
import subprocess
import sys

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, production_settings_errors

STRONG_KEY = "k" * 30 + "Zq8#Lm2!Pw9$Rt5^Xy7&Bn3*Vc6(Hj"


def test_production_settings_accept_safe_values():
    assert (
        production_settings_errors(
            debug=False, secret_key=STRONG_KEY, allowed_hosts=["erp.example.com"]
        )
        == []
    )


@pytest.mark.parametrize(
    ("debug", "secret_key", "allowed_hosts"),
    [
        (True, STRONG_KEY, ["erp.example.com"]),
        (False, "short", ["erp.example.com"]),
        (False, "dev-only-" + "x" * 60, ["erp.example.com"]),
        (False, "django-insecure-" + "x" * 60, ["erp.example.com"]),
        (False, STRONG_KEY, []),
        (False, STRONG_KEY, ["*"]),
    ],
)
def test_production_settings_reject_unsafe_values(debug, secret_key, allowed_hosts):
    assert production_settings_errors(
        debug=debug, secret_key=secret_key, allowed_hosts=allowed_hosts
    )


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("0", False), ("Yes", True)])
def test_env_bool_parses_common_values(monkeypatch, raw, expected):
    monkeypatch.setenv("SOME_FLAG", raw)
    assert env_bool("SOME_FLAG") is expected


def test_env_bool_rejects_garbage(monkeypatch):
    monkeypatch.setenv("SOME_FLAG", "maybe")
    with pytest.raises(ImproperlyConfigured):
        env_bool("SOME_FLAG")


def test_api_is_closed_by_default():
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


def test_database_is_postgresql():
    # Constraints, row-level security and NUMERIC behaviour must be tested on PostgreSQL.
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


def _load_settings_in_subprocess(**overrides: str):
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **overrides}
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_production_startup_refuses_debug_mode():
    result = _load_settings_in_subprocess(
        DJANGO_ENV="production",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY=STRONG_KEY,
        DJANGO_ALLOWED_HOSTS="erp.example.com",
    )
    assert result.returncode != 0
    assert "DJANGO_DEBUG must be false" in result.stderr


def test_production_startup_accepts_safe_configuration():
    result = _load_settings_in_subprocess(
        DJANGO_ENV="production",
        DJANGO_DEBUG="false",
        DJANGO_SECRET_KEY=STRONG_KEY,
        DJANGO_ALLOWED_HOSTS="erp.example.com",
    )
    assert result.returncode == 0, result.stderr
