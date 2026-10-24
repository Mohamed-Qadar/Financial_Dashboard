"""Environment variable helpers and startup safety checks.

This module must not import Django models: it is loaded by settings before apps are ready.
"""

import os

from django.core.exceptions import ImproperlyConfigured

INSECURE_SECRET_PREFIXES = ("django-insecure", "dev-only", "change-me")
MIN_SECRET_KEY_LENGTH = 50


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
