import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_create_user_normalizes_email_and_hashes_password():
    user = User.objects.create_user("  Amina@Example.COM ", password="correct horse 42")

    assert user.email == "amina@example.com"
    assert user.password != "correct horse 42"
    assert user.check_password("correct horse 42")
    assert not user.is_staff
    assert not user.is_superuser


def test_create_user_without_password_is_unusable():
    user = User.objects.create_user("no-password@example.com")

    assert not user.has_usable_password()


def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user("", password="whatever-123")


def test_email_is_unique_case_insensitively():
    User.objects.create_user("hodan@example.com")

    with pytest.raises(IntegrityError):
        User.objects.create(email="HODAN@example.com")


def test_authentication_by_email_ignores_case():
    User.objects.create_user("farah@example.com", password="s3cure-pass-phrase")

    assert authenticate(username="FARAH@example.com", password="s3cure-pass-phrase") is not None
    assert authenticate(username="farah@example.com", password="wrong-password") is None


def test_inactive_user_cannot_authenticate():
    User.objects.create_user("inactive@example.com", password="s3cure-pass-phrase", is_active=False)

    assert authenticate(username="inactive@example.com", password="s3cure-pass-phrase") is None


def test_superuser_flags():
    admin = User.objects.create_superuser("root@example.com", password="s3cure-pass-phrase")

    assert admin.is_staff and admin.is_superuser


def test_user_ids_are_uuids():
    user = User.objects.create_user("uuid@example.com")

    assert len(str(user.pk)) == 36
