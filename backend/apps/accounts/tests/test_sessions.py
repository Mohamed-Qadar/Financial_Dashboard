import time
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.accounts.tests.conftest import logged_in_client

pytestmark = pytest.mark.django_db

SEVEN_DAYS = 7 * 24 * 60 * 60


def _set_login_time(client, value):
    session = SessionStore(client.cookies["sessionid"].value)
    if value is None:
        del session[LOGIN_AT_SESSION_KEY]
    else:
        session[LOGIN_AT_SESSION_KEY] = value
    session.save()


def test_session_limits_are_configured_as_decided():
    assert settings.SESSION_COOKIE_AGE == 12 * 60 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is True
    assert settings.SESSION_ABSOLUTE_MAX_AGE == SEVEN_DAYS
    assert settings.PASSWORD_RESET_TIMEOUT == 60 * 60


def test_idle_timeout_is_extended_by_activity(user):
    client = logged_in_client()
    key = client.cookies["sessionid"].value
    Session.objects.filter(session_key=key).update(expire_date=timezone.now() + timedelta(hours=1))

    assert client.get(reverse("auth-me")).status_code == 200

    expire = Session.objects.get(session_key=key).expire_date
    assert expire > timezone.now() + timedelta(hours=11)


def test_idle_session_past_its_expiry_is_rejected(user):
    client = logged_in_client()
    key = client.cookies["sessionid"].value
    Session.objects.filter(session_key=key).update(
        expire_date=timezone.now() - timedelta(seconds=1)
    )

    assert client.get(reverse("auth-me")).status_code == 403


def test_session_within_seven_days_is_accepted(user):
    client = logged_in_client()
    _set_login_time(client, int(time.time()) - SEVEN_DAYS + 60)

    assert client.get(reverse("auth-me")).status_code == 200


def test_session_older_than_seven_days_is_ended_despite_activity(user):
    client = logged_in_client()
    key = client.cookies["sessionid"].value
    _set_login_time(client, int(time.time()) - SEVEN_DAYS - 1)

    response = client.get(reverse("auth-me"))

    assert response.status_code == 403
    assert not Session.objects.filter(session_key=key).exists()


@pytest.mark.parametrize("value", [None, "yesterday"])
def test_session_without_a_valid_login_time_is_treated_as_expired(user, value):
    client = logged_in_client()
    _set_login_time(client, value)

    assert client.get(reverse("auth-me")).status_code == 403
