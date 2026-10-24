"""Authentication API (milestone 2.2, docs/SECURITY.md § 3).

Transaction pattern used by every view:
- Success: the operation and its SUCCESS audit event run in one outermost transaction
  (``transaction.atomic(durable=True)``). If the audit write fails, the operation rolls back
  and the client gets 503 ``service_unavailable``.
- Failure: the FAILURE/DENIED event is written with record_failure_event() after the failed
  work has rolled back, in its own transaction.

Views that do not require a session still enforce CSRF (``csrf_protect``): DRF only checks
CSRF for authenticated sessions, which would leave login open to login-CSRF.
"""

import logging
import time

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError, transaction
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services, throttling
from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.accounts.models import normalize_email_address
from apps.accounts.serializers import (
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserSerializer,
)
from apps.audit.events import AuditEvent, Outcome
from apps.audit.services import record_event, record_failure_event
from apps.core.client_ip import client_ip
from apps.core.exceptions import ServiceUnavailable

logger = logging.getLogger(__name__)

csrf_protected = method_decorator(csrf_protect, name="dispatch")


class InvalidCredentials(exceptions.APIException):
    # Same response for unknown e-mail, wrong password and inactive account.
    status_code = 400
    default_detail = _("Invalid email or password.")
    default_code = "invalid_credentials"


class InvalidCurrentPassword(exceptions.APIException):
    status_code = 400
    default_detail = _("The current password is incorrect.")
    default_code = "invalid_current_password"


class InvalidResetLink(exceptions.APIException):
    status_code = 400
    default_detail = _("This password reset link is invalid or has expired.")
    default_code = "invalid_reset_link"


def _user_target(user_id) -> dict:
    return {"target_type": "user", "target_id": user_id or ""}


def _ip_identifier(request: Request) -> str:
    return client_ip(request) or "unknown"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the CSRF cookie; clients send its value back in the X-CSRFToken header."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses={204: None}, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_204_NO_CONTENT)


@csrf_protected
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: UserSerializer}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = normalize_email_address(serializer.validated_data["email"])
        password = serializer.validated_data["password"]

        ip = _ip_identifier(request)
        throttling.enforce(
            request,
            [
                (throttling.LOGIN_PER_IP, ip),
                (throttling.LOGIN_PER_ACCOUNT_AND_IP_MINUTE, f"{email}|{ip}"),
                (throttling.LOGIN_PER_ACCOUNT_AND_IP_HOUR, f"{email}|{ip}"),
                (throttling.LOGIN_PER_ACCOUNT, email),
            ],
            AuditEvent.LOGIN_THROTTLED,
        )

        django_request = request._request
        user = authenticate(django_request, username=email, password=password)
        if user is None:
            record_failure_event(
                AuditEvent.LOGIN_FAILED,
                request=request,
                metadata={"reason": "invalid_credentials"},
                **_user_target(services.find_user_id(email)),
            )
            raise InvalidCredentials()

        try:
            with transaction.atomic(durable=True):
                record_event(
                    AuditEvent.LOGIN_SUCCEEDED,
                    Outcome.SUCCESS,
                    request=request,
                    actor=user,
                    **_user_target(user.pk),
                )
                login(django_request, user)
                django_request.session[LOGIN_AT_SESSION_KEY] = int(time.time())
        except DatabaseError:
            # Never leave an authenticated session that has no audit entry.
            self._discard_session(django_request)
            record_failure_event(
                AuditEvent.LOGIN_FAILED,
                request=request,
                metadata={"reason": "storage_unavailable"},
                **_user_target(user.pk),
            )
            raise ServiceUnavailable() from None

        return Response(UserSerializer(user).data)

    @staticmethod
    def _discard_session(django_request) -> None:
        try:
            django_request.session.flush()
        except DatabaseError:
            django_request.session.clear()
        django_request.user = AnonymousUser()


@csrf_protected
class LogoutView(APIView):
    """Always answers 204 so it reveals nothing about the session."""

    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        user = request.user
        if user.is_authenticated:
            try:
                with transaction.atomic(durable=True):
                    record_event(
                        AuditEvent.LOGOUT,
                        Outcome.SUCCESS,
                        request=request,
                        actor=user,
                        **_user_target(user.pk),
                    )
                    logout(request._request)
            except DatabaseError:
                record_failure_event(
                    AuditEvent.LOGOUT,
                    request=request,
                    actor=user,
                    metadata={"reason": "storage_unavailable"},
                    **_user_target(user.pk),
                )
                raise ServiceUnavailable() from None
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UserSerializer}, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)


class PasswordChangeView(APIView):
    """Keeps the current session; every other session of the user stops working."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        throttling.enforce(
            request,
            [
                (throttling.PASSWORD_CHANGE_PER_USER_MINUTE, str(user.pk)),
                (throttling.PASSWORD_CHANGE_PER_USER_HOUR, str(user.pk)),
            ],
            AuditEvent.PASSWORD_CHANGE_THROTTLED,
        )

        if not user.check_password(serializer.validated_data["current_password"]):
            record_failure_event(
                AuditEvent.PASSWORD_CHANGE_FAILED,
                request=request,
                actor=user,
                metadata={"reason": "invalid_current_password"},
                **_user_target(user.pk),
            )
            raise InvalidCurrentPassword()

        new_password = serializer.validated_data["new_password"]
        services.check_new_password(new_password, user)
        try:
            with transaction.atomic(durable=True):
                user.set_password(new_password)
                user.save(update_fields=["password"])
                record_event(
                    AuditEvent.PASSWORD_CHANGED,
                    Outcome.SUCCESS,
                    request=request,
                    actor=user,
                    **_user_target(user.pk),
                )
                # New session key + new auth hash for this session; other sessions keep the
                # old hash and are rejected on their next request.
                update_session_auth_hash(request._request, user)
        except DatabaseError:
            record_failure_event(
                AuditEvent.PASSWORD_CHANGE_FAILED,
                request=request,
                actor=user,
                metadata={"reason": "storage_unavailable"},
                **_user_target(user.pk),
            )
            raise ServiceUnavailable() from None
        return Response(status=status.HTTP_204_NO_CONTENT)


@csrf_protected
class PasswordResetRequestView(APIView):
    """Always 202 (unless rate-limited), whether or not the account exists."""

    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetRequestSerializer, responses={202: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = normalize_email_address(serializer.validated_data["email"])
        throttling.enforce(
            request,
            [
                (throttling.RESET_REQUEST_PER_IP, _ip_identifier(request)),
                (throttling.RESET_REQUEST_PER_EMAIL, email),
            ],
            AuditEvent.PASSWORD_RESET_THROTTLED,
        )

        user = services.user_for_password_reset(email)
        if user is None:
            record_failure_event(
                AuditEvent.PASSWORD_RESET_REQUESTED,
                request=request,
                metadata={"reason": "no_eligible_account"},
                **_user_target(services.find_user_id(email)),
            )
            return Response(status=status.HTTP_202_ACCEPTED)

        try:
            with transaction.atomic(durable=True):
                record_event(
                    AuditEvent.PASSWORD_RESET_REQUESTED,
                    Outcome.SUCCESS,
                    request=request,
                    **_user_target(user.pk),
                )
                # Only e-mail a link whose request was audited.
                transaction.on_commit(lambda: self._send(request, user))
        except DatabaseError:
            # No audit entry, so no e-mail. The response stays 202 so that a storage
            # failure does not reveal which addresses have accounts.
            record_failure_event(
                AuditEvent.PASSWORD_RESET_REQUESTED,
                request=request,
                metadata={"reason": "storage_unavailable"},
                **_user_target(user.pk),
            )
        return Response(status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _send(request: Request, user) -> None:
        try:
            services.send_password_reset_email(user)
        except Exception:
            logger.exception("password reset e-mail could not be sent")
            record_failure_event(
                AuditEvent.PASSWORD_RESET_EMAIL_FAILED, request=request, **_user_target(user.pk)
            )


@csrf_protected
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        throttling.enforce(
            request,
            [(throttling.RESET_CONFIRM_PER_IP, _ip_identifier(request))],
            AuditEvent.PASSWORD_RESET_THROTTLED,
        )

        data = serializer.validated_data
        user = services.user_from_reset_link(data["uid"], data["token"])
        if user is None:
            record_failure_event(
                AuditEvent.PASSWORD_RESET_FAILED,
                request=request,
                metadata={"reason": "invalid_or_expired_link"},
            )
            raise InvalidResetLink()

        services.check_new_password(data["new_password"], user)
        try:
            with transaction.atomic(durable=True):
                # Changing the password also invalidates this link and every session.
                user.set_password(data["new_password"])
                user.save(update_fields=["password"])
                record_event(
                    AuditEvent.PASSWORD_RESET_COMPLETED,
                    Outcome.SUCCESS,
                    request=request,
                    actor=user,
                    **_user_target(user.pk),
                )
        except DatabaseError:
            record_failure_event(
                AuditEvent.PASSWORD_RESET_FAILED,
                request=request,
                metadata={"reason": "storage_unavailable"},
                **_user_target(user.pk),
            )
            raise ServiceUnavailable() from None
        return Response(status=status.HTTP_204_NO_CONTENT)
