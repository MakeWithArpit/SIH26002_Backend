from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from apps.common.responses import standard_response

class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return standard_response(
            data={
                "status": "healthy",
                "service": "SIH26002 Backend",
                "version": "v1.0.0",
                "phase": "Phase 0 - Foundation"
            }
        )
