from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import User, normalize_email_address
from apps.accounts.serializers import password_field
from apps.organizations.models import Company
from apps.tenants.models import Tenant


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = password_field()
    full_name = serializers.CharField(max_length=200)
    business_name = serializers.CharField(max_length=200)
    language = serializers.ChoiceField(choices=User.Language.choices, default=User.Language.SOMALI)

    def validate(self, attrs: dict) -> dict:
        # The validators compare the password with the e-mail and name of the future user.
        candidate = get_user_model()(
            email=normalize_email_address(attrs["email"]), full_name=attrs["full_name"]
        )
        try:
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


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
