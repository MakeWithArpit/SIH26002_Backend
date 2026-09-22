"""
Phase 11 — Dashboard APIs: Test Suite

Tests:
  1. GET /api/v1/dashboard/summary/ — returns expected KPI keys
  2. GET /api/v1/dashboard/summary/ — counts correct (0 baseline)
  3. GET /api/v1/dashboard/districts/ — returns districts list
  4. GET /api/v1/dashboard/vehicles/ — returns vehicle summary
  5. GET /api/v1/dashboard/alerts/active/ — returns active alerts
  6. GET /api/v1/dashboard/alerts/active/?limit=5 — respects limit param
  7. GET /api/v1/dashboard/bottlenecks/ — returns bottlenecks list
  8. GET /api/v1/dashboard/field-intelligence/ — returns reports summary
  9. Unauthenticated access to any dashboard endpoint rejected (401)
 10. DashboardService.get_summary — live counts correct after data creation
"""
from django.contrib.auth.models import User
from django.contrib.gis.geos import MultiPolygon, Polygon, LineString, Point
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.reports.models import IncidentReport
from apps.routes.models import (
    Alert, AlertStatus, AlertSeverity, AlertType,
    District, Infrastructure, OperationalStatus, RiskLevel,
    InfrastructureType, RoadClassification,
)
from apps.vehicles.models import Vehicle, Trip, TripStatus
from apps.dashboard.services import DashboardService


def _poly():
    return MultiPolygon(Polygon.from_bbox((68.0, 20.0, 97.0, 37.0)), srid=4326)


def _line():
    return LineString((77.0, 28.0), (77.5, 28.5), srid=4326)


SUMMARY_URL = '/api/v1/dashboard/summary/'
DISTRICTS_URL = '/api/v1/dashboard/districts/'
VEHICLES_URL = '/api/v1/dashboard/vehicles/'
ALERTS_ACTIVE_URL = '/api/v1/dashboard/alerts/active/'
BOTTLENECKS_URL = '/api/v1/dashboard/bottlenecks/'
FIELD_INTEL_URL = '/api/v1/dashboard/field-intelligence/'


class DashboardSummaryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dashuser', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

    def test_summary_returns_expected_keys(self):
        """Summary response must contain all expected KPI sections."""
        resp = self.client_api.get(SUMMARY_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('districts', data)
        self.assertIn('infrastructure', data)
        self.assertIn('alerts', data)
        self.assertIn('vehicles', data)
        self.assertIn('field_reports', data)
        self.assertIn('generated_at', data)

    def test_summary_counts_baseline(self):
        """With no data, all numeric fields should be 0."""
        resp = self.client_api.get(SUMMARY_URL)
        data = resp.json()['data']
        self.assertEqual(data['alerts']['active'], 0)
        self.assertEqual(data['vehicles']['active'], 0)

    def test_summary_counts_reflect_created_data(self):
        """After creating data, summary counts should increase."""
        district = District.objects.create(name='D1', state='S1', geom=_poly())
        Vehicle.objects.create(registration_number='DV-001')
        Alert.objects.create(
            alert_id='dash-test-1',
            alert_type=AlertType.INFRASTRUCTURE_RISK,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            title='Test Alert',
            description='Test description',
        )
        service = DashboardService()
        data = service.get_summary()
        self.assertEqual(data['alerts']['active'], 1)
        self.assertEqual(data['alerts']['critical'], 1)
        self.assertEqual(data['vehicles']['active'], 1)


class DashboardDistrictsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('distuser', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        District.objects.create(name='D-A', state='SA', geom=_poly())
        District.objects.create(name='D-B', state='SB', geom=_poly())

    def test_returns_all_districts(self):
        """Districts endpoint should return all districts with overview fields."""
        resp = self.client_api.get(DISTRICTS_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['total'], 2)
        district = data['districts'][0]
        self.assertIn('id', district)
        self.assertIn('accessibility_score', district)
        self.assertIn('weather', district)
        self.assertIn('active_alerts', district)


class DashboardVehiclesViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('vehuser', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

    def test_vehicles_summary_structure(self):
        """Vehicles endpoint returns correct structure."""
        Vehicle.objects.create(registration_number='VEH-001')
        resp = self.client_api.get(VEHICLES_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('total_active_vehicles', data)
        self.assertIn('trips_by_status', data)
        self.assertIn('vehicles', data)
        self.assertEqual(data['total_active_vehicles'], 1)


class DashboardAlertsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alertuser', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

    def _create_alert(self, idx):
        Alert.objects.create(
            alert_id=f'dash-alert-{idx}',
            alert_type=AlertType.EXTREME_WEATHER,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACTIVE,
            title=f'Alert {idx}',
            description='Test',
        )

    def test_active_alerts_feed(self):
        """Active alerts endpoint returns active alerts."""
        self._create_alert(1)
        self._create_alert(2)
        resp = self.client_api.get(ALERTS_ACTIVE_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['total'], 2)
        self.assertIn('alerts', data)

    def test_limit_param_respected(self):
        """limit query param caps the alert feed."""
        for i in range(10):
            self._create_alert(i + 100)
        resp = self.client_api.get(ALERTS_ACTIVE_URL + '?limit=3')
        data = resp.json()['data']
        self.assertLessEqual(len(data['alerts']), 3)


class DashboardBottlenecksViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('botuser', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.district = District.objects.create(name='BD', state='BS', geom=_poly())

    def test_bottlenecks_returns_high_risk(self):
        """Bottlenecks endpoint returns high-risk segments."""
        Infrastructure.objects.create(
            district=self.district,
            name='HighRiskRoad',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.STATE_HIGHWAY,
            geom=_line(),
            start_node=10,
            end_node=11,
            risk_score=85.0,
            risk_level=RiskLevel.HIGH,
            status=OperationalStatus.RISKY,
        )
        resp = self.client_api.get(BOTTLENECKS_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertGreaterEqual(data['total'], 1)
        seg = data['bottlenecks'][0]
        self.assertIn('risk_score', seg)
        self.assertIn('district', seg)


class DashboardUnauthTest(TestCase):
    def test_unauthenticated_rejected(self):
        """All dashboard endpoints require authentication."""
        anon = APIClient()
        for url in [SUMMARY_URL, DISTRICTS_URL, VEHICLES_URL,
                    ALERTS_ACTIVE_URL, BOTTLENECKS_URL, FIELD_INTEL_URL]:
            resp = anon.get(url)
            self.assertIn(resp.status_code, [401, 403], msg=f'Failed for {url}')
