from drf_spectacular.authentication import SessionScheme


class CsrfSessionScheme(SessionScheme):
    """Describe apps.accounts.authentication.SessionAuthentication as cookie auth in OpenAPI."""

    target_class = "apps.accounts.authentication.SessionAuthentication"
