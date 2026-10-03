from rest_framework import serializers

from .models import Alert, ScheduledReport


class WatchlistWriteSerializer(serializers.Serializer):
    repository_id = serializers.IntegerField(min_value=1)


class AlertQuerySerializer(serializers.Serializer):
    repository_id = serializers.IntegerField(required=False, min_value=1)
    status = serializers.ChoiceField(required=False, choices=Alert.Status.choices)
    alert_type = serializers.ChoiceField(required=False, choices=Alert.Type.choices)


class AlertStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(Alert.Status.READ, Alert.Status.DISMISSED))


class ReportQuerySerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(required=False, choices=ScheduledReport.Type.choices)


class ReportGenerateSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(choices=ScheduledReport.Type.choices)
