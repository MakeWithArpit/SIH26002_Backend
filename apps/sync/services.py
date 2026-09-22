"""
Phase 9 — Offline Sync: SyncService

Handles idempotent processing of batch sync records using:
  - client_sync_id for deduplication
  - Last-Write-Wins (LWW) for duplicate resolution by client_timestamp
"""
import logging
import uuid
from typing import Any, Dict, List

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.db import transaction

from apps.reports.models import IncidentReport
from apps.vehicles.models import LocationPing, Vehicle

logger = logging.getLogger(__name__)


class SyncService:
    """
    Processes a validated batch of offline sync records idempotently.

    Returns a list of per-record results:
      { client_id, status, server_id? }

    Status values:
      created           - new record persisted
      duplicate_skipped - client_id already exists, skipped
      error             - validation or DB error
    """

    SUPPORTED_TYPES = ('incident_report', 'location_ping')

    def process_batch(
        self,
        records: List[Dict[str, Any]],
        requesting_user: User,
    ) -> Dict[str, Any]:
        results = []
        created_count = 0
        skipped_count = 0
        error_count = 0

        # Sort by client_timestamp so LWW ordering is preserved within batch
        sorted_records = sorted(records, key=lambda r: r['client_timestamp'])

        for record in sorted_records:
            client_id = record['client_id']
            record_type = record['record_type']

            try:
                with transaction.atomic():
                    if record_type == 'incident_report':
                        result = self._process_incident_report(
                            client_id, record['data'], requesting_user
                        )
                    elif record_type == 'location_ping':
                        result = self._process_location_ping(
                            client_id, record['data']
                        )
                    else:
                        result = {
                            'client_id': str(client_id),
                            'status': 'error',
                            'error': f'Unknown record_type: {record_type}',
                        }

                if result['status'] == 'created':
                    created_count += 1
                elif result['status'] == 'duplicate_skipped':
                    skipped_count += 1
                else:
                    error_count += 1

                results.append(result)

            except Exception as exc:
                logger.error(
                    'SyncService error processing client_id=%s type=%s: %s',
                    client_id, record_type, exc
                )
                error_count += 1
                results.append({
                    'client_id': str(client_id),
                    'status': 'error',
                    'error': str(exc),
                })

        return {
            'results': results,
            'total': len(records),
            'created': created_count,
            'skipped': skipped_count,
            'errors': error_count,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_incident_report(
        self,
        client_id: uuid.UUID,
        data: Dict[str, Any],
        officer: User,
    ) -> Dict[str, Any]:
        """Create IncidentReport idempotently. Skip if client_id already known."""

        # Deduplication check
        if IncidentReport.objects.filter(client_sync_id=client_id).exists():
            return {'client_id': str(client_id), 'status': 'duplicate_skipped'}

        location = Point(
            float(data['longitude']),
            float(data['latitude']),
            srid=4326,
        )
        report = IncidentReport.objects.create(
            officer=officer,
            photo_url=data['photo_url'],
            location=location,
            description=data.get('description', ''),
            incident_type=data['incident_type'],
            severity=data['severity'],
            client_timestamp=data['client_timestamp'],
            client_sync_id=client_id,
        )
        return {
            'client_id': str(client_id),
            'status': 'created',
            'server_id': report.pk,
            'record_type': 'incident_report',
        }

    def _process_location_ping(
        self,
        client_id: uuid.UUID,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create LocationPing idempotently. Skip if client_id already known."""

        # Deduplication check
        if LocationPing.objects.filter(client_sync_id=client_id).exists():
            return {'client_id': str(client_id), 'status': 'duplicate_skipped'}

        try:
            vehicle = Vehicle.objects.get(pk=data['vehicle_id'])
        except Vehicle.DoesNotExist:
            return {
                'client_id': str(client_id),
                'status': 'error',
                'error': f"Vehicle {data['vehicle_id']} not found",
            }

        location = Point(
            float(data['longitude']),
            float(data['latitude']),
            srid=4326,
        )
        ping = LocationPing.objects.create(
            vehicle=vehicle,
            location=location,
            speed=float(data.get('speed', 0.0)),
            timestamp=data['timestamp'],
            client_sync_id=client_id,
        )

        # Keep Vehicle cached telemetry up to date (LWW — only update if newer)
        if vehicle.last_ping_time is None or data['timestamp'] >= vehicle.last_ping_time:
            Vehicle.objects.filter(pk=vehicle.pk).update(
                current_lat=data['latitude'],
                current_lng=data['longitude'],
                current_speed=data.get('speed', 0.0),
                current_location=location,
                last_ping_time=data['timestamp'],
            )

        return {
            'client_id': str(client_id),
            'status': 'created',
            'server_id': ping.pk,
            'record_type': 'location_ping',
        }
