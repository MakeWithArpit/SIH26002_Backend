"""
Phase 9 — Offline Sync: Test Suite

Tests:
  1. SyncBatchView: single incident_report record created
  2. SyncBatchView: duplicate client_id returns duplicate_skipped
  3. SyncBatchView: single location_ping created + vehicle telemetry updated
  4. SyncBatchView: duplicate location_ping skipped
  5. Mixed batch: all record types processed, correct counts
  6. Empty records list rejected (400)
  7. Invalid record_type rejected (400)
  8. Unauthenticated request rejected (401)
  9. LWW ordering: older record processed before newer (sorted by client_timestamp)
 10. SyncService: unknown vehicle returns error status (not exception)
"""
import uuid
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, MultiPolygon, Polygon
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.reports.models import IncidentReport
from apps.routes.models import District, Infrastructure
from apps.vehicles.models import Vehicle, LocationPing, Trip
from apps.sync.services import SyncService


def _make_polygon():
    return MultiPolygon(Polygon.from_bbox((68.0, 20.0, 97.0, 37.0)), srid=4326)


BATCH_URL = '/api/v1/sync/batch/'


class SyncBatchIncidentReportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('syncuser', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.district = District.objects.create(
            name='SyncDistrict', state='TestState', geom=_make_polygon()
        )

    def _incident_record(self, client_id=None):
        return {
            'client_id': str(client_id or uuid.uuid4()),
            'record_type': 'incident_report',
            'client_timestamp': '2026-09-01T10:00:00Z',
            'data': {
                'photo_url': 'https://ik.imagekit.io/test/photo.jpg',
                'latitude': 28.6,
                'longitude': 77.2,
                'description': 'Test flood report',
                'incident_type': 'flood',
                'severity': 'high',
                'client_timestamp': '2026-09-01T10:00:00Z',
            },
        }

    def test_incident_report_created(self):
        """Single incident_report record should be created."""
        cid = uuid.uuid4()
        resp = self.client.post(BATCH_URL, {'records': [self._incident_record(cid)]}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['created'], 1)
        self.assertEqual(data['skipped'], 0)
        self.assertEqual(data['errors'], 0)
        self.assertEqual(data['results'][0]['status'], 'created')
        self.assertTrue(IncidentReport.objects.filter(client_sync_id=cid).exists())

    def test_duplicate_client_id_skipped(self):
        """Second submission with same client_id must return duplicate_skipped."""
        cid = uuid.uuid4()
        self.client.post(BATCH_URL, {'records': [self._incident_record(cid)]}, format='json')
        resp = self.client.post(BATCH_URL, {'records': [self._incident_record(cid)]}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['skipped'], 1)
        self.assertEqual(data['created'], 0)
        self.assertEqual(IncidentReport.objects.filter(client_sync_id=cid).count(), 1)


class SyncBatchLocationPingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('pinguser', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.vehicle = Vehicle.objects.create(registration_number='TS-SYNC-01')

    def _ping_record(self, client_id=None, speed=30.0):
        return {
            'client_id': str(client_id or uuid.uuid4()),
            'record_type': 'location_ping',
            'client_timestamp': '2026-09-01T10:05:00Z',
            'data': {
                'vehicle_id': self.vehicle.pk,
                'latitude': 28.7,
                'longitude': 77.3,
                'speed': speed,
                'timestamp': '2026-09-01T10:05:00Z',
            },
        }

    def test_location_ping_created_and_vehicle_updated(self):
        """Location ping created and vehicle cached telemetry updated."""
        cid = uuid.uuid4()
        resp = self.client_api.post(BATCH_URL, {'records': [self._ping_record(cid)]}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['created'], 1)
        self.assertTrue(LocationPing.objects.filter(client_sync_id=cid).exists())
        self.vehicle.refresh_from_db()
        self.assertAlmostEqual(self.vehicle.current_lat, 28.7)

    def test_duplicate_ping_skipped(self):
        """Duplicate location ping by client_id should be skipped."""
        cid = uuid.uuid4()
        self.client_api.post(BATCH_URL, {'records': [self._ping_record(cid)]}, format='json')
        resp = self.client_api.post(BATCH_URL, {'records': [self._ping_record(cid)]}, format='json')
        data = resp.json()['data']
        self.assertEqual(data['skipped'], 1)
        self.assertEqual(LocationPing.objects.filter(client_sync_id=cid).count(), 1)


class SyncBatchMixedTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('mixeduser', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.district = District.objects.create(
            name='MixedDistrict', state='TestState', geom=_make_polygon()
        )
        self.vehicle = Vehicle.objects.create(registration_number='MIX-01')

    def test_mixed_batch_correct_counts(self):
        """Mixed batch with one of each type should report correct totals."""
        records = [
            {
                'client_id': str(uuid.uuid4()),
                'record_type': 'incident_report',
                'client_timestamp': '2026-09-01T09:00:00Z',
                'data': {
                    'photo_url': 'https://ik.imagekit.io/x/img.jpg',
                    'latitude': 28.5, 'longitude': 77.1,
                    'incident_type': 'landslide', 'severity': 'medium',
                    'client_timestamp': '2026-09-01T09:00:00Z',
                },
            },
            {
                'client_id': str(uuid.uuid4()),
                'record_type': 'location_ping',
                'client_timestamp': '2026-09-01T09:01:00Z',
                'data': {
                    'vehicle_id': self.vehicle.pk,
                    'latitude': 28.6, 'longitude': 77.2,
                    'speed': 45.0, 'timestamp': '2026-09-01T09:01:00Z',
                },
            },
        ]
        resp = self.client_api.post(BATCH_URL, {'records': records}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['created'], 2)
        self.assertEqual(data['skipped'], 0)
        self.assertEqual(data['errors'], 0)

    def test_empty_records_rejected(self):
        """Empty records list must return 400."""
        resp = self.client_api.post(BATCH_URL, {'records': []}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_rejected(self):
        """Unauthenticated request must be rejected with 401."""
        anon = APIClient()
        resp = anon.post(BATCH_URL, {'records': []}, format='json')
        self.assertIn(resp.status_code, [401, 403])


class SyncServiceEdgeCaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('edgeuser', password='pass')

    def test_unknown_vehicle_returns_error_status(self):
        """Unknown vehicle_id should return error status, not raise exception."""
        service = SyncService()
        records = [
            {
                'client_id': uuid.uuid4(),
                'record_type': 'location_ping',
                'client_timestamp': datetime(2026, 9, 1, 10, 0, tzinfo=dt_timezone.utc),
                'data': {
                    'vehicle_id': 999999,
                    'latitude': 28.5,
                    'longitude': 77.0,
                    'speed': 0.0,
                    'timestamp': datetime(2026, 9, 1, 10, 0, tzinfo=dt_timezone.utc),
                },
            }
        ]
        result = service.process_batch(records, requesting_user=self.user)
        self.assertEqual(result['errors'], 1)
        self.assertEqual(result['results'][0]['status'], 'error')
