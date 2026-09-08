"""
API View for IMD District-wise Weather Warnings.
"""
from datetime import datetime, timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from .services.imd_service import (
    IMDWarningService,
    CACHE_KEY_DATA,
    CACHE_KEY_TIME,
    CACHE_KEY_STALE_DATA,
    CACHE_KEY_STALE_TIME,
)


class AlertsView(APIView):
    """
    Retrieve live normalized weather warnings from the official IMD District Warning API.
    Filtered specifically to Northeast India (NER) logistics demonstration districts.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get IMD District Weather Warnings",
        description="Returns normalized 5-day weather alerts from the official IMD District Warning API for NER corridor districts.",
        parameters=[
            OpenApiParameter(name="force_refresh", type=bool, required=False, description="Force fresh fetch from IMD skipping cache"),
            OpenApiParameter(name="severity", type=str, required=False, description="Filter by severity (High, Medium, Low)"),
            OpenApiParameter(name="district", type=str, required=False, description="Filter by district name"),
        ],
        responses={200: OpenApiResponse(description="Alert list retrieved"), 503: OpenApiResponse(description="IMD unavailable")},
        tags=["Alerts"]
    )
    def get(self, request, *args, **kwargs):
        force_refresh = request.query_params.get("force_refresh", "false").lower() in ("true", "1")
        severity_filter = request.query_params.get("severity", "").strip().capitalize()
        district_filter = request.query_params.get("district", "").strip().lower()

        result = IMDWarningService.fetch_warnings(force_refresh=force_refresh)

        if not result.get("success") and not result.get("alerts"):
            return Response(result, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        alerts = result.get("alerts", [])

        if severity_filter and severity_filter in ("High", "Medium", "Low"):
            alerts = [a for a in alerts if a.get("severity") == severity_filter]

        if district_filter:
            alerts = [a for a in alerts if district_filter in a.get("district", "").lower()]

        response_data = {
            "success": True,
            "source": result.get("source", "India Meteorological Department (IMD)"),
            "total": len(alerts),
            "total_unfiltered": result.get("total", len(alerts)),
            "last_updated": result.get("last_updated"),
            "cached": result.get("cached", False),
            "alerts": alerts,
        }
        if "warning" in result:
            response_data["warning"] = result["warning"]

        return Response(response_data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Seed Realistic IMD Warning Cache (Demo/Fallback)",
        description="Populates the backend cache with realistic IMD NER corridor records when live external credentials are not present.",
        tags=["Alerts"]
    )
    def post(self, request, *args, **kwargs):
        sample_imd_records = [
            {
                "Obj_id": "573",
                "District": "East Khasi Hills",
                "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "UTC": "03:00",
                "Day_1": "16",
                "Day1_Color": 1,
                "Day_2": "2,4",
                "Day2_Color": 2,
                "Day_3": "4",
                "Day3_Color": 3,
                "Day_4": "1",
                "Day4_Color": 4,
                "Day_5": "1",
                "Day5_Color": 4,
            },
            {
                "Obj_id": "302",
                "District": "Ri-Bhoi",
                "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "UTC": "03:00",
                "Day_1": "4",
                "Day1_Color": 2,
                "Day_2": "2",
                "Day2_Color": 3,
                "Day_3": "1",
                "Day3_Color": 4,
                "Day_4": "1",
                "Day4_Color": 4,
                "Day_5": "1",
                "Day5_Color": 4,
            },
            {
                "Obj_id": "301",
                "District": "Kamrup Metropolitan",
                "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "UTC": "03:00",
                "Day_1": "2",
                "Day1_Color": 2,
                "Day_2": "1",
                "Day2_Color": 4,
                "Day_3": "1",
                "Day3_Color": 4,
                "Day_4": "1",
                "Day4_Color": 4,
                "Day_5": "1",
                "Day5_Color": 4,
            },
            {
                "Obj_id": "315",
                "District": "Karbi Anglong",
                "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "UTC": "03:00",
                "Day_1": "2",
                "Day1_Color": 3,
                "Day_2": "1",
                "Day2_Color": 4,
                "Day_3": "1",
                "Day3_Color": 4,
                "Day_4": "1",
                "Day4_Color": 4,
                "Day_5": "1",
                "Day5_Color": 4,
            },
            {
                "Obj_id": "410",
                "District": "Dimapur",
                "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "UTC": "03:00",
                "Day_1": "8",
                "Day1_Color": 3,
                "Day_2": "1",
                "Day2_Color": 4,
                "Day_3": "1",
                "Day3_Color": 4,
                "Day_4": "1",
                "Day4_Color": 4,
                "Day_5": "1",
                "Day5_Color": 4,
            },
        ]
        alerts = IMDWarningService.normalize_records(sample_imd_records)
        now_iso = datetime.now(timezone.utc).isoformat()
        cache.set(CACHE_KEY_DATA, alerts, timeout=600)
        cache.set(CACHE_KEY_TIME, now_iso, timeout=600)
        cache.set(CACHE_KEY_STALE_DATA, alerts, timeout=86400)
        cache.set(CACHE_KEY_STALE_TIME, now_iso, timeout=86400)
        return Response({
            "success": True,
            "message": "Demo IMD warnings cached successfully",
            "total": len(alerts),
            "last_updated": now_iso,
            "alerts": alerts,
        }, status=status.HTTP_200_OK)
