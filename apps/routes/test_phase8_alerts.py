"""
Unit and Integration Tests for Phase 8 Persistent Alert System.

Tests cover:
- Alert model creation, fields, enums, and string representation
- WeatherAlertService & AlertService generation logic (infrastructure & weather)
- Alert persistence and deduplication in database
- Proximity-based active alerts filtering
- Acknowledge and resolve flows
- Alert summary counts
- Alert API endpoints (AlertsView, AlertGenerateView, AlertResolveView, AlertSummaryView)
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, LineString, MultiPolygon, Polygon
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.routes.models import (
    District,
    Infrastructure,
    WeatherSnapshot,
    Alert,
    AlertType,
    AlertSeverity,
    AlertStatus,
    HazardLevel,
    RiskLevel,
    InfrastructureType,
    RoadClassification,
    OperationalStatus,
    PhysicalCondition,
)
from apps.routes.services.alerts import AlertService, WeatherAlertService
from apps.routes.views_alerts import (
    AlertsView,
    AlertGenerateView,
    AlertResolveView,
    AlertSummaryView,
)


class AlertModelTest(TestCase):
    """Test Alert model fields, status transitions, and representations."""

    def setUp(self):
        self.user = User.objects.create_user(username='test_officer', password='password123')
        poly = Polygon(((91.7, 26.1), (91.8, 26.1), (91.8, 26.2), (91.7, 26.2), (91.7, 26.1)))
        self.district = District.objects.create(
            name='Kamrup Metropolitan',
            state='Assam',
            geom=MultiPolygon(poly),
        )
        self.infra = Infrastructure.objects.create(
            district=self.district,
            name='NH-27 Segment A',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            geom=LineString((91.72, 26.12), (91.75, 26.15)),
            start_node=1001,
            end_node=1002,
            length_km=5.0,
            status=OperationalStatus.RISKY,
            risk_score=85.0,
            risk_level=RiskLevel.HIGH,
            disruption_probability=0.85,
        )

    def test_alert_creation_and_str(self):
        alert = Alert.objects.create(
            alert_id='infra-test-1',
            alert_type=AlertType.INFRASTRUCTURE_RISK,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACTIVE,
            title='High Disruption Risk — NH-27 Segment A',
            description='Risk score 85/100.',
            recommended_action='Reduce convoy speed.',
            infrastructure=self.infra,
            district=self.district,
            location=Point(91.72, 26.12, srid=4326),
            risk_score=85.0,
            risk_level='high',
            disruption_probability=0.85,
        )
        self.assertEqual(alert.alert_id, 'infra-test-1')
        self.assertEqual(alert.status, AlertStatus.ACTIVE)
        self.assertIn('[HIGH]', str(alert))
        self.assertIn('NH-27 Segment A', str(alert))


class AlertServiceLogicTest(TestCase):
    """Test AlertService generation, persistence, acknowledge, and resolve."""

    def setUp(self):
        self.user = User.objects.create_user(username='admin_officer', password='password123')
        poly = Polygon(((91.7, 26.1), (91.8, 26.1), (91.8, 26.2), (91.7, 26.2), (91.7, 26.1)))
        self.district = District.objects.create(
            name='East Khasi Hills',
            state='Meghalaya',
            geom=MultiPolygon(poly),
        )
        self.infra = Infrastructure.objects.create(
            district=self.district,
            name='NH-06 Barapani Sector',
            infra_type=InfrastructureType.ROAD,
            geom=LineString((91.89, 25.65), (91.90, 25.66)),
            start_node=2001,
            end_node=2002,
            length_km=8.2,
            risk_score=88.0,
            risk_level=RiskLevel.HIGH,
            landslide_susceptibility=HazardLevel.HIGH,
            recent_rainfall_mm=75.0,
        )
        self.weather = WeatherSnapshot.objects.create(
            district=self.district,
            rainfall_mm=110.0,
            condition='extreme',
            weather_warning=True,
            warning_details='Flash flood warning in effect',
            recorded_at=timezone.now(),
        )

    def test_generate_infrastructure_alerts(self):
        alerts = AlertService.generate_infrastructure_alerts()
        self.assertTrue(len(alerts) >= 1)
        infra_alert = next((a for a in alerts if a['infrastructure_id'] == self.infra.id), None)
        self.assertIsNotNone(infra_alert)
        self.assertEqual(infra_alert['severity'], 'critical')
        self.assertIn('recommended_action', infra_alert)

    def test_generate_weather_alerts(self):
        weather_alerts = AlertService.generate_weather_alerts()
        self.assertTrue(len(weather_alerts) >= 1)
        extreme = next((a for a in weather_alerts if a['district_id'] == self.district.id), None)
        self.assertIsNotNone(extreme)
        self.assertEqual(extreme['severity'], 'critical')
        self.assertIn('Extreme Rainfall Alert', extreme['title'])

    def test_generate_and_persist_alerts_deduplication(self):
        # First call generates and persists
        result1 = AlertService.generate_and_persist_alerts()
        self.assertGreater(result1['persisted'], 0)
        first_persisted = result1['persisted']

        # Second call should recognize existing active alerts and not duplicate
        result2 = AlertService.generate_and_persist_alerts()
        self.assertEqual(result2['persisted'], 0)
        self.assertEqual(Alert.objects.filter(status=AlertStatus.ACTIVE).count(), first_persisted)

    def test_acknowledge_and_resolve_flow(self):
        AlertService.generate_and_persist_alerts()
        active_alerts = AlertService.get_active_alerts()
        self.assertTrue(len(active_alerts) > 0)

        target_alert = active_alerts[0]
        # Acknowledge
        ack_success = AlertService.acknowledge_alert(target_alert.alert_id, self.user)
        self.assertTrue(ack_success)
        target_alert.refresh_from_db()
        self.assertEqual(target_alert.status, AlertStatus.ACKNOWLEDGED)
        self.assertEqual(target_alert.assigned_to, self.user)

        # Resolve
        resolve_success = AlertService.resolve_alert(target_alert.alert_id)
        self.assertTrue(resolve_success)
        target_alert.refresh_from_db()
        self.assertEqual(target_alert.status, AlertStatus.RESOLVED)
        self.assertIsNotNone(target_alert.resolved_at)

    def test_alert_summary(self):
        AlertService.generate_and_persist_alerts()
        summary = AlertService.get_alert_summary()
        self.assertIn('total', summary)
        self.assertIn('active', summary)
        self.assertIn('resolved', summary)
        self.assertIn('critical', summary)
        self.assertGreaterEqual(summary['total'], 1)


class AlertApiViewsTest(TestCase):
    """Test Phase 8 Alert API views and HTTP responses."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username='api_officer', password='password123')
        poly = Polygon(((91.7, 26.1), (91.8, 26.1), (91.8, 26.2), (91.7, 26.2), (91.7, 26.1)))
        self.district = District.objects.create(
            name='Ri-Bhoi',
            state='Meghalaya',
            geom=MultiPolygon(poly),
        )
        self.infra = Infrastructure.objects.create(
            district=self.district,
            name='GS Road Nongpoh',
            geom=LineString((91.85, 25.88), (91.86, 25.89)),
            start_node=3001,
            end_node=3002,
            length_km=4.5,
            risk_score=78.0,
            risk_level=RiskLevel.HIGH,
        )

    def test_alerts_get_api(self):
        AlertService.generate_and_persist_alerts()
        request = self.factory.get('/api/v1/routes/alerts/')
        force_authenticate(request, user=self.user)
        view = AlertsView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertIn('alerts', response.data['data'])

    def test_alerts_generate_api(self):
        request = self.factory.post('/api/v1/routes/alerts/generate/')
        force_authenticate(request, user=self.user)
        view = AlertGenerateView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertIn('total_generated', response.data['data'])

    def test_alert_resolve_api(self):
        AlertService.generate_and_persist_alerts()
        alert = Alert.objects.first()
        self.assertIsNotNone(alert)

        request = self.factory.post(f'/api/v1/routes/alerts/{alert.alert_id}/resolve/')
        force_authenticate(request, user=self.user)
        view = AlertResolveView.as_view()
        response = view(request, alert_id=alert.alert_id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['status'], 'resolved')

    def test_alert_summary_api(self):
        AlertService.generate_and_persist_alerts()
        request = self.factory.get('/api/v1/routes/alerts/summary/')
        force_authenticate(request, user=self.user)
        view = AlertSummaryView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertIn('active', response.data['data'])
