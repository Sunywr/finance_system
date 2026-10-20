from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "display_name",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "last_login",
        ]
        read_only_fields = ["id", "username", "is_staff", "is_superuser", "last_login"]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        validate_password(value, self.context.get("request").user)
        return value
