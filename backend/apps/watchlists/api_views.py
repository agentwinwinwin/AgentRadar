from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_serializers import (
    AlertQuerySerializer,
    AlertStatusSerializer,
    ReportGenerateSerializer,
    ReportQuerySerializer,
    WatchlistWriteSerializer,
)
from .api_services import alert_data, report_data, watchlist_item
from .models import AlertReceipt, ScheduledReport
from .services import ReportService, WatchlistService


class WatchlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"results": [watchlist_item(item) for item in WatchlistService.list(request.user)]}
        )

    def post(self, request):
        serializer = WatchlistWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item, created = WatchlistService.add(
            serializer.validated_data["repository_id"], request.user
        )
        return Response(watchlist_item(item), status=status.HTTP_201_CREATED if created else 200)


class WatchlistItemView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, repository_id: int):
        removed = WatchlistService.remove(repository_id, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT if removed else status.HTTP_404_NOT_FOUND)


class AlertListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = AlertQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = AlertReceipt.objects.filter(owner=request.user).select_related(
            "alert", "alert__repository"
        )
        for field in ("status",):
            if serializer.validated_data.get(field) is not None:
                queryset = queryset.filter(**{field: serializer.validated_data[field]})
        if serializer.validated_data.get("repository_id") is not None:
            queryset = queryset.filter(
                alert__repository_id=serializer.validated_data["repository_id"]
            )
        if serializer.validated_data.get("alert_type") is not None:
            queryset = queryset.filter(alert__alert_type=serializer.validated_data["alert_type"])
        return Response(
            {"results": [alert_data(receipt.alert, receipt.status) for receipt in queryset[:200]]}
        )


class AlertDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, alert_id: int):
        receipt = get_object_or_404(
            AlertReceipt.objects.select_related("alert", "alert__repository"),
            alert_id=alert_id,
            owner=request.user,
        )
        return Response(alert_data(receipt.alert, receipt.status))

    def patch(self, request, alert_id: int):
        serializer = AlertStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = get_object_or_404(
            AlertReceipt.objects.select_related("alert", "alert__repository"),
            alert_id=alert_id,
            owner=request.user,
        )
        receipt.status = serializer.validated_data["status"]
        receipt.save(update_fields=("status", "updated_at"))
        return Response(alert_data(receipt.alert, receipt.status))


class ReportListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ReportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = ScheduledReport.objects.filter(owner=request.user)
        if report_type := serializer.validated_data.get("report_type"):
            queryset = queryset.filter(report_type=report_type)
        return Response({"results": [report_data(report) for report in queryset[:100]]})

    def post(self, request):
        serializer = ReportGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            report_data(
                ReportService.generate(serializer.validated_data["report_type"], request.user)
            ),
            status=status.HTTP_201_CREATED,
        )


class ReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id: int):
        report = get_object_or_404(ScheduledReport, pk=report_id, owner=request.user)
        return Response(report_data(report))
