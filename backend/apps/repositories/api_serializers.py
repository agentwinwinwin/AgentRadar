from rest_framework import serializers

from apps.repositories.models import RepositoryCategory
from apps.trends.models import LifecycleStage


class ProjectDiscoverQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=False, max_length=200)
    category = serializers.ChoiceField(required=False, choices=RepositoryCategory.choices)
    language = serializers.CharField(required=False, max_length=100)
    license = serializers.CharField(required=False, max_length=100)
    min_stars = serializers.IntegerField(required=False, min_value=0)
    max_stars = serializers.IntegerField(required=False, min_value=0)
    trend_min = serializers.FloatField(required=False, min_value=0, max_value=100)
    potential_min = serializers.FloatField(required=False, min_value=0, max_value=100)
    learning_min = serializers.FloatField(required=False, min_value=0, max_value=100)
    enterprise_min = serializers.FloatField(required=False, min_value=0, max_value=100)
    lifecycle = serializers.ChoiceField(required=False, choices=LifecycleStage.choices)
    sort = serializers.ChoiceField(
        required=False,
        default="-trend",
        choices=(
            "trend",
            "-trend",
            "potential",
            "-potential",
            "learning",
            "-learning",
            "enterprise",
            "-enterprise",
            "stars",
            "-stars",
            "updated",
            "-updated",
        ),
    )

    def validate(self, attrs):
        if (
            attrs.get("min_stars") is not None
            and attrs.get("max_stars") is not None
            and attrs["min_stars"] > attrs["max_stars"]
        ):
            raise serializers.ValidationError("min_stars must be less than or equal to max_stars")
        return attrs


class MetricsQuerySerializer(serializers.Serializer):
    range = serializers.ChoiceField(choices=("7d", "30d", "90d"), default="30d")
