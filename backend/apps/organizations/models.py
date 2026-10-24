"""Companies (legal entities of a tenant) and their branches.

Branch management endpoints arrive in milestone 2.5; 2.3a only creates the tables.
"""

from django.db import models

from apps.finance.models import Currency
from apps.tenants.models import TenantOwnedModel


class Company(TenantOwnedModel):
    code = models.CharField(max_length=20)
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True, default="")
    # Immutable once something has been posted in it (enforced when postings exist).
    base_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        db_column="base_currency_code",
        related_name="+",
    )
    country_code = models.CharField(max_length=2, default="SO")
    tax_id = models.CharField(max_length=50, blank=True, default="")
    timezone = models.CharField(max_length=50, default="Africa/Mogadishu")
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        db_table = "companies"
        verbose_name_plural = "companies"
        constraints = [
            *TenantOwnedModel.Meta.constraints,
            models.UniqueConstraint(fields=["tenant", "code"], name="companies_tenant_code"),
            models.CheckConstraint(
                condition=models.Q(fiscal_year_start_month__gte=1, fiscal_year_start_month__lte=12),
                name="companies_fiscal_month_range",
            ),
            models.CheckConstraint(
                condition=models.Q(country_code__regex=r"^[A-Z]{2}$"),
                name="companies_country_code_iso",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.legal_name}"


class Branch(TenantOwnedModel):
    # Also covered by the composite key (tenant_id, company_id) -> companies (tenant_id, id).
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="branches")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=500, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        db_table = "branches"
        verbose_name_plural = "branches"
        constraints = [
            *TenantOwnedModel.Meta.constraints,
            models.UniqueConstraint(fields=["company", "code"], name="branches_company_code"),
            # Target for later composite keys that must stay inside one company.
            models.UniqueConstraint(fields=["company", "id"], name="branches_company_id_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"
