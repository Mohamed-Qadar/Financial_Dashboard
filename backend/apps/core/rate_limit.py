"""Concurrency-safe fixed-window rate limiting in PostgreSQL.

Each attempt increments a counter with a single ``INSERT ... ON CONFLICT DO UPDATE ...
RETURNING``, which PostgreSQL serializes per row, so N concurrent attempts produce counts
1..N and exactly ``limit`` of them are allowed. (Django's cache ``incr`` is read-then-write
and can be overrun by concurrent requests.)

Counters are written in their own outermost transaction so they persist even when the
request that triggered them fails or rolls back.

Trade-off: fixed windows allow up to 2x ``limit`` attempts around a window boundary.
"""

import hashlib
import hmac
import math
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from django.conf import settings
from django.db import connection, transaction

PURGE_PROBABILITY = 0.01

UPSERT_SQL = """
    INSERT INTO rate_limit_counters (key, scope, window_start, count, expires_at)
    VALUES (%s, %s, %s, 1, %s)
    ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limit_counters.count + 1
    RETURNING count
"""


@dataclass(frozen=True)
class RateLimit:
    scope: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    scope: str
    count: int
    limit: int
    retry_after: int

    @property
    def allowed(self) -> bool:
        return self.count <= self.limit

    @property
    def first_exceeded(self) -> bool:
        """True only for the first rejected attempt of a window (to avoid audit flooding)."""
        return self.count == self.limit + 1


def _now() -> float:
    """Clock used for windows (a separate function so tests can pin it)."""
    return time.time()


def _key(scope: str, identifier: str) -> str:
    message = f"{scope}\x00{identifier}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def hit(rule: RateLimit, identifier: str) -> RateLimitResult:
    """Count one attempt against ``rule`` for ``identifier`` and report whether it is allowed."""
    now = _now()
    window_start = math.floor(now / rule.window_seconds) * rule.window_seconds
    window_end = window_start + rule.window_seconds
    with transaction.atomic(durable=True), connection.cursor() as cursor:
        cursor.execute(
            UPSERT_SQL,
            [
                _key(rule.scope, identifier),
                rule.scope,
                datetime.fromtimestamp(window_start, tz=UTC),
                datetime.fromtimestamp(window_end, tz=UTC),
            ],
        )
        (count,) = cursor.fetchone()
    if random.random() < PURGE_PROBABILITY:  # noqa: S311 - not security sensitive
        purge_expired()
    return RateLimitResult(
        scope=rule.scope,
        count=count,
        limit=rule.limit,
        retry_after=max(1, math.ceil(window_end - now)),
    )


def purge_expired() -> int:
    with transaction.atomic(durable=True), connection.cursor() as cursor:
        cursor.execute("DELETE FROM rate_limit_counters WHERE expires_at < now()")
        return cursor.rowcount
