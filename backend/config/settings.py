"""Django settings for Somali ERP.

All environment-specific values come from environment variables (see ../.env.example).
DJANGO_ENV selects behaviour: "development", "test" or "production".
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import env, env_bool, env_list, production_settings_errors

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", required=True),
        "USER": env("POSTGRES_USER", required=True),
        "PASSWORD": env("POSTGRES_PASSWORD", required=True),
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
        "rest_framework.authentication.SessionAuthentication",
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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
