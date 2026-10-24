import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, connections

from apps.core.models import RateLimitCounter
from apps.core.rate_limit import RateLimit, hit, purge_expired

RULE = RateLimit("test_scope", limit=5, window_seconds=60)

pytestmark = pytest.mark.usefixtures("pinned_rate_limit_clock")


@pytest.mark.django_db
def test_counts_up_and_blocks_after_the_limit():
    results = [hit(RULE, "someone") for _ in range(7)]

    assert [r.count for r in results] == [1, 2, 3, 4, 5, 6, 7]
    assert [r.allowed for r in results] == [True] * 5 + [False] * 2
    assert [r.first_exceeded for r in results] == [False] * 5 + [True, False]
    assert all(1 <= r.retry_after <= 60 for r in results)


@pytest.mark.django_db
def test_identifiers_and_scopes_are_independent():
    for _ in range(5):
        hit(RULE, "a")

    assert hit(RULE, "b").allowed
    assert hit(RateLimit("other_scope", 5, 60), "a").allowed
    assert not hit(RULE, "a").allowed


@pytest.mark.django_db
def test_raw_identifiers_are_not_stored():
    hit(RULE, "hodan@example.com")

    [row] = RateLimitCounter.objects.all()
    assert "hodan" not in row.key
    assert len(row.key) == 64


@pytest.mark.django_db
def test_expired_counters_are_purged():
    hit(RULE, "a")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE rate_limit_counters SET expires_at = now() - interval '1 second'")

    assert purge_expired() == 1
    assert RateLimitCounter.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_attempts_never_exceed_the_limit():
    """30 truly parallel attempts (separate DB connections): exactly 5 are allowed."""
    attempts = 30
    barrier = threading.Barrier(attempts)

    def attempt(_):
        try:
            barrier.wait()
            return hit(RULE, "parallel")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        results = list(pool.map(attempt, range(attempts)))

    assert sorted(r.count for r in results) == list(range(1, attempts + 1))
    assert sum(r.allowed for r in results) == RULE.limit
    assert sum(r.first_exceeded for r in results) == 1
