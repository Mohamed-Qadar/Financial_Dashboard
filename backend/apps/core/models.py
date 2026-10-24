from django.db import models


class RateLimitCounter(models.Model):
    """Fixed-window attempt counters (see apps.core.rate_limit).

    ``key`` is an HMAC of the scope and identifier, so the table holds no e-mail addresses
    or IP addresses.
    """

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=64)
    scope = models.CharField(max_length=50)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField()
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "rate_limit_counters"
        constraints = [
            models.UniqueConstraint(fields=["key", "window_start"], name="rate_limit_key_window"),
        ]
        indexes = [models.Index(fields=["expires_at"], name="rate_limit_expires_idx")]

    def __str__(self) -> str:
        return f"{self.scope} {self.window_start:%Y-%m-%d %H:%M} = {self.count}"
