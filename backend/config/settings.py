"""Django settings for Somali ERP.

All environment-specific values come from environment variables (see ../.env.example).
DJANGO_ENV selects behaviour: "development", "test" or "production".
"""

import ipaddress
import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import (
    env,
    env_bool,
    env_list,
    production_auth_errors,
    production_database_errors,
    production_settings_errors,
)

BASE_DIR = Path(__file__).resolve().parent.parent

ENVIRONMENT = env("DJANGO_ENV", "development")
if ENVIRONMENT not in {"development", "test", "production"}:
    raise ImproperlyConfigured(f"Unknown DJANGO_ENV {ENVIRONMENT!r}.")
IS_PRODUCTION = ENVIRONMENT == "production"

DEBUG = env_bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

if IS_PRODUCTION:
    errors = production_settings_errors(
        debug=DEBUG, secret_key=SECRET_KEY, allowed_hosts=ALLOWED_HOSTS
    )
    if errors:
        raise ImproperlyConfigured("Unsafe production settings: " + " ".join(errors))

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.audit",
]

MIDDLEWARE = [
    # First, so every response and log line carries the request ID.
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.AbsoluteSessionLifetimeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

# Two database roles (see docs/SECURITY.md):
# - "owner": owns the schema; used for migrations, management commands and creating test databases.
# - "app":   the web process; not a superuser, cannot bypass row-level security, no DDL.
# The default is the restricted role, so forgetting the variable never grants owner rights.
DB_ROLE = env("DJANGO_DB_ROLE", "app")
if DB_ROLE not in {"app", "owner"}:
    raise ImproperlyConfigured(f"DJANGO_DB_ROLE must be 'app' or 'owner', got {DB_ROLE!r}.")
DATABASE_APP_ROLE = env("POSTGRES_APP_USER", "somali_erp_app")
# The role name is interpolated into GRANT/CREATE ROLE statements; allow only plain identifiers.
if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", DATABASE_APP_ROLE):
    raise ImproperlyConfigured("POSTGRES_APP_USER must match [a-z_][a-z0-9_]{0,62}.")
# Optional for owner-role processes, except ensure_db_roles which sets it on the app role.
DATABASE_APP_PASSWORD = os.environ.get("POSTGRES_APP_PASSWORD") or None
if DB_ROLE == "app":
    if DATABASE_APP_PASSWORD is None:
        raise ImproperlyConfigured("Environment variable POSTGRES_APP_PASSWORD is required.")
    _db_user, _db_password = DATABASE_APP_ROLE, DATABASE_APP_PASSWORD
else:
    _db_user = env("POSTGRES_USER", required=True)
    _db_password = env("POSTGRES_PASSWORD", required=True)
if env("POSTGRES_USER", "") == DATABASE_APP_ROLE:
    raise ImproperlyConfigured("POSTGRES_APP_USER must be a different role than POSTGRES_USER.")

if IS_PRODUCTION:
    errors = production_database_errors(app_password=DATABASE_APP_PASSWORD)
    if errors:
        raise ImproperlyConfigured("Unsafe production settings: " + " ".join(errors))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", required=True),
        "USER": _db_user,
        "PASSWORD": _db_password,
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(env("POSTGRES_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": 5},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization: English is the source language; Somali translations follow in Phase 2.
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("so", "Soomaali")]
TIME_ZONE = "UTC"  # Stored in UTC; displayed in the company's timezone (default Africa/Mogadishu).
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.SessionAuthentication",
    ],
    # Closed by default: every endpoint must deliberately opt out of authentication.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    # Decimals are serialized as strings so no precision is lost in JSON clients.
    "COERCE_DECIMAL_TO_STRING": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Somali ERP API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": (
        ["rest_framework.permissions.IsAdminUser"]
        if IS_PRODUCTION
        else ["rest_framework.permissions.AllowAny"]
    ),
}

# --- Authentication (milestone 2.2; docs/SECURITY.md § 3) ---
# Argon2 first; older hashes still verify and are upgraded on the next successful login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
# Idle timeout: 12 hours, refreshed by every request. Absolute limit: 7 days after login,
# enforced by apps.accounts.middleware.AbsoluteSessionLifetimeMiddleware.
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_ABSOLUTE_MAX_AGE = 7 * 24 * 60 * 60
PASSWORD_RESET_TIMEOUT = 60 * 60
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"

FRONTEND_BASE_URL = env("DJANGO_FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
# Development prints e-mails (including reset links) to the log; production must not.
EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", "Somali ERP <no-reply@localhost>")

# Proxies whose X-Forwarded-For is believed (CIDR list). Empty = trust none. The Next.js
# rewrite proxy must NOT be listed on its own: it forwards client-supplied headers unchanged.
try:
    TRUSTED_PROXIES = [
        ipaddress.ip_network(cidr, strict=False) for cidr in env_list("DJANGO_TRUSTED_PROXIES")
    ]
except ValueError as exc:
    raise ImproperlyConfigured(f"DJANGO_TRUSTED_PROXIES: {exc}") from exc

if IS_PRODUCTION:
    errors = production_auth_errors(
        email_backend=EMAIL_BACKEND,
        trusted_proxies_configured="DJANGO_TRUSTED_PROXIES" in os.environ,
        frontend_base_url=FRONTEND_BASE_URL,
    )
    if errors:
        raise ImproperlyConfigured("Unsafe production settings: " + " ".join(errors))

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if IS_PRODUCTION:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = int(env("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # HSTS preload is hard to undo; enable it deliberately once the production domain is final.
    SILENCED_SYSTEM_CHECKS = ["security.W021"]
    if env_bool("DJANGO_BEHIND_TLS_PROXY", default=False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# JSON lines by default (machine-readable, injection-safe); "text" is easier to read locally.
LOG_FORMAT = env("DJANGO_LOG_FORMAT", "json")
if LOG_FORMAT not in {"json", "text"}:
    raise ImproperlyConfigured(f"DJANGO_LOG_FORMAT must be 'json' or 'text', got {LOG_FORMAT!r}.")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.structured_logging.RequestIDFilter"},
    },
    "formatters": {
        "json": {"()": "apps.core.structured_logging.JSONFormatter"},
        "text": {
            "format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
