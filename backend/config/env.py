"""Environment variable helpers and startup safety checks.

This module must not import Django models: it is loaded by settings before apps are ready.
"""

import os

from django.core.exceptions import ImproperlyConfigured

INSECURE_SECRET_PREFIXES = ("django-insecure", "dev-only", "change-me", "ci-only")
MIN_SECRET_KEY_LENGTH = 50
MIN_DB_PASSWORD_LENGTH = 16


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if value is None or (required and value == ""):
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"Environment variable {name} must be a boolean, got {value!r}.")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def production_settings_errors(
    *, debug: bool, secret_key: str, allowed_hosts: list[str]
) -> list[str]:
    """Return the reasons why these settings are unsafe for production (empty if safe)."""
    errors = []
    if debug:
        errors.append("DJANGO_DEBUG must be false in production.")
    if len(secret_key) < MIN_SECRET_KEY_LENGTH or secret_key.lower().startswith(
        INSECURE_SECRET_PREFIXES
    ):
        errors.append(
            f"DJANGO_SECRET_KEY must be a random value of at least {MIN_SECRET_KEY_LENGTH} "
            "characters and must not be a development placeholder."
        )
    if not allowed_hosts or "*" in allowed_hosts:
        errors.append("DJANGO_ALLOWED_HOSTS must list explicit host names in production.")
    return errors


def production_database_errors(*, app_password: str | None) -> list[str]:
    """Return the reasons why the runtime database password is unsafe for production."""
    if app_password is None:
        return []  # Owner-role processes (migrations) may run without the runtime password.
    if len(app_password) < MIN_DB_PASSWORD_LENGTH or app_password.lower().startswith(
        INSECURE_SECRET_PREFIXES
    ):
        return [
            f"POSTGRES_APP_PASSWORD must be a random value of at least {MIN_DB_PASSWORD_LENGTH} "
            "characters and must not be a development placeholder."
        ]
    return []


INSECURE_EMAIL_BACKENDS = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
)


def production_auth_errors(
    *, email_backend: str, trusted_proxies_configured: bool, frontend_base_url: str
) -> list[str]:
    """Return the reasons why authentication settings are unsafe for production."""
    errors = []
    if email_backend in INSECURE_EMAIL_BACKENDS:
        errors.append(
            "DJANGO_EMAIL_BACKEND must deliver e-mail in production; the console/file/memory "
            "backends would expose password-reset links or drop them."
        )
    if not trusted_proxies_configured:
        errors.append(
            "DJANGO_TRUSTED_PROXIES must be set explicitly in production (an empty value means "
            "'trust no proxy'); see docs/SECURITY.md, Client IP addresses."
        )
    if not frontend_base_url.startswith("https://"):
        errors.append("DJANGO_FRONTEND_BASE_URL must use https:// in production.")
    return errors
