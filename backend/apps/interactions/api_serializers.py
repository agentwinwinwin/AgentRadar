from rest_framework import serializers


class RepositoryCommentCreateSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=2000, trim_whitespace=True)

