import time

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import AnonymousUser

# Unix time of the login that created this session; set by the login view.
LOGIN_AT_SESSION_KEY = "_auth_login_at"


class AbsoluteSessionLifetimeMiddleware:
    """End authenticated sessions SESSION_ABSOLUTE_MAX_AGE seconds after login.

    The idle timeout (SESSION_COOKIE_AGE, refreshed on every request) alone would let an
    active session live forever. Sessions without a login time are treated as expired.
    Must come after AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session = request.session
        if SESSION_KEY in session:
            login_at = session.get(LOGIN_AT_SESSION_KEY)
            expired = (
                not isinstance(login_at, int | float)
                or time.time() - login_at > settings.SESSION_ABSOLUTE_MAX_AGE
            )
            if expired:
                session.flush()
                request.user = AnonymousUser()
        return self.get_response(request)
