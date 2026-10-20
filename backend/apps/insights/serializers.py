from rest_framework import serializers

from apps.common.utils.crypto import decrypt_text, encrypt_text, mask_secret

from .models import AIAnalysis, AIProviderConfig
from .services import generate_analysis


class AIProviderConfigSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = AIProviderConfig
        fields = [
            "id",
            "name",
            "base_url",
            "api_key",
            "api_key_masked",
            "model",
            "temperature",
            "max_tokens",
            "timeout_seconds",
            "max_retries",
            "retry_wait_seconds",
            "is_default",
            "enabled",
            "extra_headers",
            "extra_body",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "api_key_masked", "created_at", "updated_at"]

    def get_api_key_masked(self, obj):
        return mask_secret(decrypt_text(obj.api_key_encrypted))

    def validate_base_url(self, value):
        if not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("Base URL 必须以 http:// 或 https:// 开头")
        return value.rstrip("/")

    def validate_temperature(self, value):
        if value < 0 or value > 2:
            raise serializers.ValidationError("temperature 必须在 0-2 之间")
        return value

    def validate_max_tokens(self, value):
        if value < 32 or value > 32000:
            raise serializers.ValidationError("max_tokens 必须在 32-32000 之间")
        return value

    def validate_max_retries(self, value):
        if value < 0 or value > 5:
            raise serializers.ValidationError("重试次数必须在 0-5 之间")
        return value

    def validate_retry_wait_seconds(self, value):
        if value < 1 or value > 300:
            raise serializers.ValidationError("重试等待秒数必须在 1-300 之间")
        return value

    def validate_extra_body(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("额外请求体必须是 JSON 对象")
        return value

    def _apply_key(self, validated_data):
        key = validated_data.pop("api_key", None)
        if key:
            validated_data["api_key_encrypted"] = encrypt_text(key)
        return validated_data

    def create(self, validated_data):
        validated_data = self._apply_key(validated_data)
        provider = super().create(validated_data)
        if provider.is_default:
            AIProviderConfig.objects.filter(owner=provider.owner).exclude(id=provider.id).update(is_default=False)
        return provider

    def update(self, instance, validated_data):
        validated_data = self._apply_key(validated_data)
        provider = super().update(instance, validated_data)
        if provider.is_default:
            AIProviderConfig.objects.filter(owner=provider.owner).exclude(id=provider.id).update(is_default=False)
        return provider


class AIAnalysisListSerializer(serializers.ModelSerializer):
    analysis_type_label = serializers.CharField(source="get_analysis_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    provider_name = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = AIAnalysis
        fields = [
            "id",
            "analysis_type",
            "analysis_type_label",
            "period_start",
            "period_end",
            "provider",
            "provider_name",
            "status",
            "status_label",
            "error",
            "tokens",
            "elapsed_ms",
            "created_at",
        ]


class AIAnalysisDetailSerializer(AIAnalysisListSerializer):
    class Meta(AIAnalysisListSerializer.Meta):
        fields = AIAnalysisListSerializer.Meta.fields + [
            "data_snapshot",
            "prompt_snapshot",
            "response_text",
        ]


class AnalysisCreateSerializer(serializers.Serializer):
    analysis_type = serializers.ChoiceField(
        choices=AIAnalysis.Type.choices, required=False, default=AIAnalysis.Type.MONTHLY
    )
    provider = serializers.PrimaryKeyRelatedField(
        queryset=AIProviderConfig.objects.none(), required=False, allow_null=True
    )
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    custom_prompt = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["provider"].queryset = AIProviderConfig.objects.filter(owner=request.user, enabled=True)

    def validate(self, attrs):
        start = attrs.get("period_start")
        end = attrs.get("period_end")
        if start and end and start > end:
            raise serializers.ValidationError("开始日期不能晚于结束日期")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return generate_analysis(owner=request.user, **validated_data)
