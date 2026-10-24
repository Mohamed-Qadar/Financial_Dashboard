import os
import subprocess
import sys

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, production_database_errors, production_settings_errors

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


STRONG_DB_PASSWORD = "Qv7#pL2!xR9$wT4^zN6&"
PRINT_DB_USER = (
    "import django; django.setup(); "
    "from django.conf import settings; print(settings.DATABASES['default']['USER'])"
)


def _load_settings_in_subprocess(*, remove=(), code="import django; django.setup()", **overrides):
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **overrides}
    for name in remove:
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


PRODUCTION = {
    "DJANGO_ENV": "production",
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": STRONG_KEY,
    "DJANGO_ALLOWED_HOSTS": "erp.example.com",
    "POSTGRES_APP_PASSWORD": STRONG_DB_PASSWORD,
    "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "DJANGO_TRUSTED_PROXIES": "",
    "DJANGO_FRONTEND_BASE_URL": "https://erp.example.com",
}


def test_production_startup_refuses_debug_mode():
    result = _load_settings_in_subprocess(**{**PRODUCTION, "DJANGO_DEBUG": "true"})
    assert result.returncode != 0
    assert "DJANGO_DEBUG must be false" in result.stderr


def test_production_startup_accepts_safe_configuration():
    result = _load_settings_in_subprocess(**PRODUCTION)
    assert result.returncode == 0, result.stderr


def test_production_startup_refuses_placeholder_app_db_password():
    result = _load_settings_in_subprocess(
        **{**PRODUCTION, "POSTGRES_APP_PASSWORD": "dev-only-app-password"}
    )
    assert result.returncode != 0
    assert "POSTGRES_APP_PASSWORD must be a random value" in result.stderr


@pytest.mark.parametrize(
    ("password", "safe"),
    [(None, True), (STRONG_DB_PASSWORD, True), ("short", False), ("ci-only-" + "x" * 20, False)],
)
def test_production_database_errors(password, safe):
    assert (production_database_errors(app_password=password) == []) is safe


def test_runtime_connects_as_app_role_by_default():
    result = _load_settings_in_subprocess(remove=["DJANGO_DB_ROLE"], code=PRINT_DB_USER)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == settings.DATABASE_APP_ROLE


def test_owner_role_is_explicit_opt_in():
    result = _load_settings_in_subprocess(DJANGO_DB_ROLE="owner", code=PRINT_DB_USER)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == os.environ["POSTGRES_USER"]


@pytest.mark.parametrize(
    ("overrides", "remove", "message"),
    [
        ({"DJANGO_DB_ROLE": "admin"}, [], "DJANGO_DB_ROLE must be 'app' or 'owner'"),
        ({"DJANGO_DB_ROLE": "app"}, ["POSTGRES_APP_PASSWORD"], "POSTGRES_APP_PASSWORD is required"),
        ({"POSTGRES_APP_USER": os.environ.get("POSTGRES_USER", "")}, [], "different role"),
        ({"POSTGRES_APP_USER": 'app"; DROP ROLE x; --'}, [], "must match"),
    ],
)
def test_invalid_database_role_configuration_is_rejected(overrides, remove, message):
    result = _load_settings_in_subprocess(remove=remove, **overrides)
    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.parametrize(
    ("overrides", "remove", "message"),
    [
        (
            {"DJANGO_EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"},
            [],
            "DJANGO_EMAIL_BACKEND must deliver e-mail",
        ),
        ({}, ["DJANGO_TRUSTED_PROXIES"], "DJANGO_TRUSTED_PROXIES must be set explicitly"),
        ({"DJANGO_FRONTEND_BASE_URL": "http://erp.example.com"}, [], "must use https://"),
    ],
)
def test_production_startup_refuses_unsafe_auth_settings(overrides, remove, message):
    result = _load_settings_in_subprocess(remove=remove, **{**PRODUCTION, **overrides})
    assert result.returncode != 0
    assert message in result.stderr


def test_invalid_trusted_proxy_network_is_rejected():
    result = _load_settings_in_subprocess(DJANGO_TRUSTED_PROXIES="10.0.0.0/8,not-a-network")
    assert result.returncode != 0
    assert "DJANGO_TRUSTED_PROXIES" in result.stderr
