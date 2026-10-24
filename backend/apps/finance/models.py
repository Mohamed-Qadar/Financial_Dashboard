"""Money concepts. Phase 2 has only the global currency reference table (decision D10)."""

from django.db import models


class Currency(models.Model):
    """ISO 4217 currency. Global reference data: seeded by migrations, read-only at runtime."""

    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    # Digits after the decimal point (USD 2, SOS 2); amounts are rounded to this.
    minor_units = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "currencies"
        verbose_name_plural = "currencies"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[A-Z]{3}$"), name="currencies_code_iso"
            ),
            models.CheckConstraint(
                condition=models.Q(minor_units__lte=4), name="currencies_minor_units_range"
            ),
        ]

    def __str__(self) -> str:
        return self.code
