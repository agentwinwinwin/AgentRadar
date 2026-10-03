from rest_framework import serializers


class ModelActivationSerializer(serializers.Serializer):
    confirmation = serializers.CharField(max_length=100)

    def validate_confirmation(self, value: str) -> str:
        expected = self.context["model_version"]
        if value != expected:
            raise serializers.ValidationError("请输入完整 model_version 以确认激活")
        return value


class TrainingStartSerializer(serializers.Serializer):
    confirmation = serializers.CharField(max_length=100)
