"""
Alert API Views for Phase 8 - Persistent Alert System.
"""
import logging
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from apps.common.responses import standard_response
from apps.routes.models import Alert, AlertStatus
from apps.routes.services.alerts import AlertService

logger = logging.getLogger(__name__)


class AlertsView(APIView):
    """
    GET /api/v1/routes/alerts/
    
    Returns active alerts from database with optional proximity filtering.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Alerts'],
        summary="Get Active Alerts (Phase 8)",
        description="Returns persisted alerts from database. Supports proximity filtering.",
        parameters=[
            OpenApiParameter(name='lat', type=float, location=OpenApiParameter.QUERY, required=False, description="Latitude"),
            OpenApiParameter(name='lng', type=float, location=OpenApiParameter.QUERY, required=False, description="Longitude"),
            OpenApiParameter(name='radius_m', type=int, location=OpenApiParameter.QUERY, required=False, description="Radius in meters (default: 50000)"),
        ],
        responses={200: OpenApiResponse(description="Active alerts retrieved")}
    )
    def get(self, request):
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        radius = float(request.GET.get('radius_m', 50000))
        
        alerts = AlertService.get_active_alerts(
            lat=float(lat) if lat else None,
            lng=float(lng) if lng else None,
            radius_m=radius
        )
        
        alert_list = []
        for a in alerts:
            alert_dict = {
                'alert_id': a.alert_id,
                'type': a.alert_type,
                'severity': a.severity,
                'title': a.title,
                'description': a.description,
                'recommended_action': a.recommended_action,
                'infrastructure_id': a.infrastructure_id,
                'risk_score': a.risk_score,
                'risk_level': a.risk_level,
                'generated_at': a.generated_at.isoformat() if a.generated_at else None,
            }
            if a.location:
                alert_dict['location'] = {'lat': a.location.y, 'lng': a.location.x}
            alert_list.append(alert_dict)
        
        return standard_response(
            data={'alerts': alert_list, 'total': len(alert_list)},
            message="Active alerts retrieved",
            status_code=status.HTTP_200_OK
        )


class AlertGenerateView(APIView):
    """
    POST /api/v1/routes/alerts/generate/
    
    Manually trigger alert generation from current conditions.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Alerts'],
        summary="Generate Alerts",
        description="Generate and persist alerts from current infrastructure risk and weather data.",
        responses={200: OpenApiResponse(description="Alerts generated")}
    )
    def post(self, request):
        result = AlertService.generate_and_persist_alerts()
        
        return standard_response(
            data=result,
            message=f"Generated {result['total_generated']} alerts, persisted {result['persisted']}",
            status_code=status.HTTP_200_OK
        )


class AlertResolveView(APIView):
    """
    POST /api/v1/routes/alerts/{alert_id}/resolve/
    
    Resolve an alert.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Alerts'],
        summary="Resolve Alert",
        description="Mark an alert as resolved.",
        responses={200: OpenApiResponse(description="Alert resolved")}
    )
    def post(self, request, alert_id):
        success = AlertService.resolve_alert(alert_id)
        
        if success:
            return standard_response(
                data={'alert_id': alert_id, 'status': 'resolved'},
                message=f"Alert {alert_id} resolved",
                status_code=status.HTTP_200_OK
            )
        else:
            return standard_response(
                success=False,
                message=f"Alert {alert_id} not found",
                status_code=status.HTTP_404_NOT_FOUND
            )


class AlertSummaryView(APIView):
    """
    GET /api/v1/routes/alerts/summary/
    
    Get alert counts by severity and status.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Alerts'],
        summary="Get Alert Summary",
        description="Get count of alerts by severity and status.",
        responses={200: OpenApiResponse(description="Alert summary retrieved")}
    )
    def get(self, request):
        summary = AlertService.get_alert_summary()
        
        return standard_response(
            data=summary,
            message="Alert summary retrieved",
            status_code=status.HTTP_200_OK
        )