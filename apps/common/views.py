import logging
from django.db import connection
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from apps.common.responses import standard_response

logger = logging.getLogger(__name__)


class APIRootView(APIView):
    """
    Root API View ('/') providing platform status and key navigation links.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        base_url = request.build_absolute_uri('/')[:-1]
        return standard_response(
            data={
                "service": "SIH26002 Backend",
                "tagline": "AI-Based Smart Logistics and Accessibility Intelligence Platform",
                "version": "v1.0.0",
                "status": "operational",
                "timestamp": timezone.now().isoformat(),
                "documentation": {
                    "swagger_ui": "/api/docs/",
                    "redoc": "/api/redoc/",
                    "openapi_schema": "/api/schema/",
                },
                "admin": "/admin/",
                "health_check": "/api/v1/health/",
                "endpoints_v1": {
                    "auth": "/api/v1/auth/",
                    "accounts": "/api/v1/accounts/",
                    "routes": "/api/v1/routes/",
                    "reports": "/api/v1/reports/",
                    "vehicles": "/api/v1/vehicles/",
                    "trips": "/api/v1/trips/",
                    "alerts": "/api/v1/alerts/",
                    "sync": "/api/v1/sync/",
                    "dashboard": "/api/v1/dashboard/",
                }
            },
            message="Welcome to SIH26002 Backend API."
        )


class HealthCheckView(APIView):
    """
    Health check endpoint for Render, Docker, and uptime monitoring.
    Verifies database connectivity.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        db_status = "healthy"
        try:
            connection.ensure_connection()
        except Exception as e:
            logger.error("Health check database error: %s", str(e))
            db_status = f"unhealthy: {str(e)}"

        is_healthy = db_status == "healthy"
        status_code = 200 if is_healthy else 503

        return standard_response(
            data={
                "status": "healthy" if is_healthy else "degraded",
                "service": "SIH26002 Backend",
                "version": "v1.0.0",
                "phase": "Phase 12 - Production Ready",
                "database": db_status,
                "timestamp": timezone.now().isoformat(),
            },
            message="System is operational." if is_healthy else "System is experiencing degradation.",
            status_code=status_code,
        )
