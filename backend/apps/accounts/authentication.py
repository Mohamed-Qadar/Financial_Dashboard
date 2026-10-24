from rest_framework import authentication, exceptions


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF session authentication whose CSRF failures use the ``csrf_failed`` error code."""

    def enforce_csrf(self, request):
        try:
            super().enforce_csrf(request)
        except exceptions.PermissionDenied as exc:
            raise exceptions.PermissionDenied(
                "CSRF verification failed.", code="csrf_failed"
            ) from exc
