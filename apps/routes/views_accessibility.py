"""
Phase 10 — Accessibility Intelligence: API Views

GET  /api/v1/routes/districts/<id>/accessibility/   → score + component breakdown
POST /api/v1/routes/districts/accessibility/refresh/ → recompute all (staff only)
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView

from apps.common.responses import standard_response
from apps.routes.models import District
from apps.routes.services.accessibility import AccessibilityService

logger = logging.getLogger(__name__)


class DistrictAccessibilityView(APIView):
    """
    GET /api/v1/routes/districts/<id>/accessibility/

    Returns the dynamic accessibility score breakdown for a specific district.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, district_id: int):
        try:
            district = District.objects.get(pk=district_id)
        except District.DoesNotExist:
            return standard_response(
                data={},
                message=f'District {district_id} not found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        service = AccessibilityService()
        breakdown = service.compute_district_score(district)

        return standard_response(
            data={
                'district_id': district.pk,
                'district_name': district.name,
                'state': district.state,
                'persisted_score': district.accessibility_score,
                'live_score': breakdown['score'],
                **breakdown,
            }
        )


class AccessibilityRefreshView(APIView):
    """
    POST /api/v1/routes/districts/accessibility/refresh/

    Recomputes and persists accessibility scores for all districts.
    Staff-only endpoint (used by Celery task or manual trigger).
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        service = AccessibilityService()
        result = service.compute_all_districts()
        logger.info('AccessibilityRefreshView: updated %d districts.', result['updated'])
        return standard_response(
            data=result,
            message=f"Accessibility scores refreshed for {result['updated']} districts.",
        )
