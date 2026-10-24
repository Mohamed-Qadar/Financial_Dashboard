from django.contrib.auth import get_user_model
from rest_framework import serializers

# Bounds the cost of hashing attacker-supplied passwords (Argon2 is deliberately expensive).
MAX_PASSWORD_LENGTH = 1024


def password_field() -> serializers.CharField:
    return serializers.CharField(
        max_length=MAX_PASSWORD_LENGTH, trim_whitespace=False, write_only=True
    )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "email", "full_name", "preferred_language"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = password_field()


class PasswordChangeSerializer(serializers.Serializer):
    current_password = password_field()
    new_password = password_field()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    new_password = password_field()
