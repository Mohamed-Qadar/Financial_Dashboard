import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connections
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts import throttling
from apps.accounts.tests.conftest import PASSWORD, audit_events, logged_in_client, login
from apps.audit.events import AuditEvent, Outcome
from apps.core.rate_limit import RateLimit

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("pinned_rate_limit_clock")]

ATTACKER_IP = "198.51.100.66"
VICTIM_IP = "203.0.113.10"


def _assert_throttled(response):
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
    assert 1 <= int(response["Retry-After"]) <= 3600


def test_sixth_attempt_per_account_and_ip_is_throttled(api, user):
    for _ in range(5):
        assert (
            login(api, "hodan@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP).status_code == 400
        )

    _assert_throttled(login(api, "hodan@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP))
    # While throttled, even the correct password is not checked from that address.
    _assert_throttled(login(api, "hodan@example.com", PASSWORD, REMOTE_ADDR=ATTACKER_IP))


def test_throttling_is_audited_once_per_window(api, user):
    for _ in range(9):
        login(api, "hodan@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP)

    [event] = audit_events(AuditEvent.LOGIN_THROTTLED)
    assert event.outcome == Outcome.DENIED
    assert event.metadata == {"limit": "login_account_ip_min"}
    assert len(audit_events(AuditEvent.LOGIN_FAILED)) == 5


def test_attacker_cannot_lock_the_owner_out_from_another_address(user):
    """Account-lockout DoS: attempts from one IP must not block the account elsewhere."""
    attacker = APIClient()
    for _ in range(25):
        login(attacker, "hodan@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP)
    _assert_throttled(login(attacker, "hodan@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP))

    response = login(APIClient(), "hodan@example.com", PASSWORD, REMOTE_ADDR=VICTIM_IP)

    assert response.status_code == 200


def test_attempts_rejected_per_ip_do_not_count_toward_the_account_wide_cap(user, monkeypatch):
    monkeypatch.setattr(throttling, "LOGIN_PER_ACCOUNT", RateLimit("login_account_hour", 8, 3600))
    attacker = APIClient()
    for _ in range(30):  # only 5 reach the account-wide counter, the rest are stopped earlier
        login(attacker, "hodan@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP)

    response = login(APIClient(), "hodan@example.com", PASSWORD, REMOTE_ADDR=VICTIM_IP)

    assert response.status_code == 200


def test_distributed_guessing_hits_the_account_wide_cap(user, monkeypatch):
    """Residual risk (documented): enough source addresses can trigger the account-wide cap."""
    monkeypatch.setattr(throttling, "LOGIN_PER_ACCOUNT", RateLimit("login_account_hour", 8, 3600))
    for i in range(8):
        login(APIClient(), "hodan@example.com", "Wrong-1", REMOTE_ADDR=f"198.51.100.{i}")

    _assert_throttled(login(APIClient(), "hodan@example.com", PASSWORD, REMOTE_ADDR=VICTIM_IP))


def test_per_ip_limit_spans_accounts(api, user):
    for i in range(30):
        login(api, f"user{i}@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP)

    _assert_throttled(login(api, "hodan@example.com", PASSWORD, REMOTE_ADDR=ATTACKER_IP))
    assert (
        login(APIClient(), "hodan@example.com", PASSWORD, REMOTE_ADDR=VICTIM_IP).status_code == 200
    )


def test_password_reset_requests_are_limited_per_email(api, user):
    for _ in range(3):
        response = api.post(
            reverse("auth-password-reset"), {"email": "hodan@example.com"}, format="json"
        )
        assert response.status_code == 202

    _assert_throttled(
        api.post(reverse("auth-password-reset"), {"email": "hodan@example.com"}, format="json")
    )
    [event] = audit_events(AuditEvent.PASSWORD_RESET_THROTTLED)
    assert event.metadata == {"limit": "reset_request_email_hour"}


def test_password_change_attempts_are_limited_per_user(user):
    client = logged_in_client()
    payload = {"current_password": "Wrong-1", "new_password": "Another-Strong-Phrase-77"}
    for _ in range(5):
        response = client.post(reverse("auth-password-change"), payload, format="json")
        assert response.status_code == 400

    _assert_throttled(client.post(reverse("auth-password-change"), payload, format="json"))


@pytest.mark.django_db(transaction=True)
def test_concurrent_login_attempts_cannot_bypass_the_limit(user):
    """20 parallel wrong-password logins for one account+IP: at most 5 are evaluated."""
    attempts = 20
    barrier = threading.Barrier(attempts)

    def attempt(_):
        try:
            client = APIClient()
            barrier.wait()
            return login(
                client, "hodan@example.com", "Wrong-1", REMOTE_ADDR=ATTACKER_IP
            ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        statuses = list(pool.map(attempt, range(attempts)))

    assert statuses.count(400) == 5
    assert statuses.count(429) == 15
    assert len(audit_events(AuditEvent.LOGIN_FAILED)) == 5
    assert len(audit_events(AuditEvent.LOGIN_THROTTLED)) == 1
