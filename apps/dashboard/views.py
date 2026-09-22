"""
Phase 11 — Dashboard & Aggregation APIs: Views

All views are GET-only, read-only, authenticated.
No write operations or new models.

Endpoints:
  GET /api/v1/dashboard/summary/
  GET /api/v1/dashboard/districts/
  GET /api/v1/dashboard/vehicles/
  GET /api/v1/dashboard/alerts/active/
  GET /api/v1/dashboard/bottlenecks/
  GET /api/v1/dashboard/field-intelligence/
"""
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.responses import standard_response
from .services import DashboardService

logger = logging.getLogger(__name__)


class DashboardSummaryView(APIView):
    """GET /api/v1/dashboard/summary/ — top-level operational KPIs."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = DashboardService()
        data = service.get_summary()
        return standard_response(data=data)


class DashboardDistrictsView(APIView):
    """GET /api/v1/dashboard/districts/ — per-district overview."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = DashboardService()
        data = service.get_districts_overview()
        return standard_response(data=data)


class DashboardVehiclesView(APIView):
    """GET /api/v1/dashboard/vehicles/ — fleet operational summary."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = DashboardService()
        data = service.get_vehicles_summary()
        return standard_response(data=data)


class DashboardActiveAlertsView(APIView):
    """GET /api/v1/dashboard/alerts/active/ — active alerts feed."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get('limit', 50)), 200)
        service = DashboardService()
        data = service.get_active_alerts_feed(limit=limit)
        return standard_response(data=data)


class DashboardBottlenecksView(APIView):
    """GET /api/v1/dashboard/bottlenecks/ — top N high-risk segments."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        top_n = min(int(request.query_params.get('top_n', 20)), 100)
        service = DashboardService()
        data = service.get_bottlenecks(top_n=top_n)
        return standard_response(data=data)


class DashboardFieldIntelligenceView(APIView):
    """GET /api/v1/dashboard/field-intelligence/ — field report summary."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get('limit', 30)), 100)
        service = DashboardService()
        data = service.get_field_intelligence_summary(limit=limit)
        return standard_response(data=data)
