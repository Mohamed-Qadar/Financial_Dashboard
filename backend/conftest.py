import pytest

# One second after a boundary of every window length used (60 s and 3600 s divide it).
PINNED_RATE_LIMIT_TIME = 1_800_000_001.0


@pytest.fixture
def pinned_rate_limit_clock(monkeypatch):
    """Keep all attempts of a test inside one rate-limit window.

    Fixed windows reset at minute/hour boundaries; without pinning, a slow test (Argon2
    hashing) that crosses a boundary would see its counter restart and fail at random.
    """
    monkeypatch.setattr("apps.core.rate_limit._now", lambda: PINNED_RATE_LIMIT_TIME)
    return PINNED_RATE_LIMIT_TIME
