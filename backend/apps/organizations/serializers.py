from rest_framework import serializers

from apps.organizations.models import Company
from apps.tenants.models import Tenant


class TenantSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name"]
        read_only_fields = fields


class CompanySerializer(serializers.ModelSerializer):
    tenant = TenantSummarySerializer(read_only=True)
    base_currency_code = serializers.CharField(source="base_currency_id", read_only=True)

    class Meta:
        model = Company
        fields = [
            "id",
            "code",
            "legal_name",
            "trade_name",
            "base_currency_code",
            "country_code",
            "timezone",
            "fiscal_year_start_month",
            "tenant",
        ]
        read_only_fields = fields
