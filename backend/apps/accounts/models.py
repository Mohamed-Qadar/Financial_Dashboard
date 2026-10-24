"""User accounts.

Users are global: one person can belong to several tenants through memberships (Phase 2).
The custom user model exists from the first migration because Django cannot switch
AUTH_USER_MODEL cleanly once the database has been migrated.
"""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def normalize_email_address(email: str) -> str:
    return email.strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra_fields) -> "User":
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=normalize_email_address(email), **extra_fields)
        user.set_password(password)  # None stores an unusable password.
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("A superuser must have is_staff=True and is_superuser=True.")
        return self.create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username: str) -> "User":
        return self.get(email=normalize_email_address(username))


class User(AbstractBaseUser, PermissionsMixin):
    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        SOMALI = "so", "Soomaali"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Stored lower-case by the manager; the Lower() constraint below also guards raw inserts.
    email = models.EmailField(_("email address"), max_length=254, unique=True)
    full_name = models.CharField(_("full name"), max_length=200, blank=True)
    preferred_language = models.CharField(
        max_length=5, choices=Language.choices, default=Language.ENGLISH
    )
    # Platform operator flag; tenant administration uses tenant roles, not this.
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="users_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email_address(self.email)
