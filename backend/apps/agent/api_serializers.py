from rest_framework import serializers


class CopilotChatSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1, max_length=4000, trim_whitespace=True)
    session_id = serializers.RegexField(r"^[A-Za-z0-9_-]{16,128}$", required=False, allow_null=True)
