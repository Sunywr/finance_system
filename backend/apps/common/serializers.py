from rest_framework import serializers


class OwnedModelSerializer(serializers.ModelSerializer):
    """Automatically assigns the request user as owner."""

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data.setdefault("owner", request.user)
        return super().create(validated_data)
