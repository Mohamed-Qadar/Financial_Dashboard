import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from apps.accounts.models import normalize_email_address

logger = logging.getLogger(__name__)


def find_user_id(email: str):
    """The id of the account with this e-mail (any state), for audit targets only."""
    User = get_user_model()
    return (
        User.objects.filter(email=normalize_email_address(email))
        .values_list("pk", flat=True)
        .first()
    )


def user_for_password_reset(email: str):
    """An active account that may reset its password, or None."""
    User = get_user_model()
    user = User.objects.filter(email=normalize_email_address(email), is_active=True).first()
    if user is None or not user.has_usable_password():
        return None
    return user


def check_new_password(password: str, user) -> None:
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"new_password": list(exc.messages)}) from exc


def password_reset_link(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"


def send_password_reset_email(user) -> None:
    send_mail(
        subject="Somali ERP password reset",
        message=(
            "A password reset was requested for your Somali ERP account.\n\n"
            f"Open this link within one hour to choose a new password:\n"
            f"{password_reset_link(user)}\n\n"
            "If you did not request this, you can ignore this e-mail."
        ),
        from_email=None,
        recipient_list=[user.email],
    )


def user_from_reset_link(uid: str, token: str):
    """The active user a valid reset link belongs to, or None (expired, used or forged)."""
    User = get_user_model()
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (ValueError, TypeError, OverflowError, DjangoValidationError, User.DoesNotExist):
        return None
    if not default_token_generator.check_token(user, token):
        return None
    return user
