"""
Phase 9 — Offline Sync: SyncBatchView

POST /api/v1/sync/batch/

Accepts a JSON batch of offline-cached records and processes them
idempotently (LWW by client_timestamp). Authentication required.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.responses import standard_response
from .serializers import SyncBatchSerializer
from .services import SyncService

logger = logging.getLogger(__name__)


class SyncBatchView(APIView):
    """
    POST /api/v1/sync/batch/

    Accepts a batch of offline-cached records from the mobile client.

    Request body:
    {
        "records": [
            {
                "client_id": "<uuid>",
                "record_type": "incident_report" | "location_ping",
                "client_timestamp": "<ISO8601>",
                "data": { ... }
            }
        ]
    }

    Response:
    {
        "success": true,
        "data": {
            "results": [ { "client_id": "...", "status": "created" | "duplicate_skipped" | "error" } ],
            "total": N,
            "created": N,
            "skipped": N,
            "errors": N
        }
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SyncBatchSerializer(data=request.data)
        if not serializer.is_valid():
            return standard_response(
                data={'errors': serializer.errors},
                message='Invalid sync batch payload.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        records = serializer.validated_data['records']
        service = SyncService()
        result = service.process_batch(records, requesting_user=request.user)

        logger.info(
            'SyncBatch processed by user=%s: total=%d created=%d skipped=%d errors=%d',
            request.user.username,
            result['total'],
            result['created'],
            result['skipped'],
            result['errors'],
        )

        return standard_response(
            data=result,
            message=f"Batch processed: {result['created']} created, {result['skipped']} skipped, {result['errors']} errors.",
            status_code=status.HTTP_200_OK,
        )
