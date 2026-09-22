"""
Phase 10 — Accessibility Intelligence: Test Suite

Tests:
  1. AccessibilityService: perfect score for all-good district
  2. AccessibilityService: degraded score for blocked segments
  3. AccessibilityService: weather penalty applied (extreme weather)
  4. AccessibilityService: empty district returns neutral score
  5. AccessibilityService: compute_all_districts updates DB
  6. AccessibilityService: connectivity status reflected in score
  7. DistrictAccessibilityView: GET returns breakdown for valid district
  8. DistrictAccessibilityView: GET 404 for unknown district
  9. AccessibilityRefreshView: staff POST triggers refresh
 10. AccessibilityRefreshView: non-staff rejected (403)
"""
from django.contrib.auth.models import User
from django.contrib.gis.geos import MultiPolygon, Polygon, LineString, Point
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.routes.models import (
    District, Infrastructure, WeatherSnapshot,
    ConnectivityStatus, PhysicalCondition, OperationalStatus, WeatherCondition,
    InfrastructureType, RoadClassification, RiskLevel,
)
from apps.routes.services.accessibility import AccessibilityService


def _poly():
    return MultiPolygon(Polygon.from_bbox((68.0, 20.0, 97.0, 37.0)), srid=4326)


def _line():
    return LineString((77.0, 28.0), (77.5, 28.5), srid=4326)


def _make_infra(district, name='Road-1', condition=PhysicalCondition.GOOD,
                op_status=OperationalStatus.ACCESSIBLE, risk_score=10.0):
    return Infrastructure.objects.create(
        district=district,
        name=name,
        infra_type=InfrastructureType.ROAD,
        road_classification=RoadClassification.NATIONAL_HIGHWAY,
        geom=_line(),
        start_node=1,
        end_node=2,
        length_km=5.0,
        condition=condition,
        status=op_status,
        risk_score=risk_score,
        risk_level=RiskLevel.LOW,
    )


def _make_weather(district, condition=WeatherCondition.CLEAR, rainfall_mm=0.0):
    return WeatherSnapshot.objects.create(
        district=district,
        rainfall_mm=rainfall_mm,
        condition=condition,
        recorded_at=timezone.now(),
    )


class AccessibilityServiceTest(TestCase):
    def setUp(self):
        self.service = AccessibilityService()
        self.district = District.objects.create(
            name='TestDist', state='TestState', geom=_poly(),
            connectivity_status=ConnectivityStatus.NORMAL,
        )

    def test_perfect_score_all_good(self):
        """All-good segments, normal connectivity, clear weather → near-perfect score."""
        _make_infra(self.district, 'Road-A', PhysicalCondition.GOOD, OperationalStatus.ACCESSIBLE, 5.0)
        _make_weather(self.district, WeatherCondition.CLEAR, 0.0)
        result = self.service.compute_district_score(self.district)
        self.assertGreater(result['score'], 8.0)

    def test_degraded_score_blocked_segments(self):
        """Blocked segments should significantly lower the score."""
        _make_infra(self.district, 'Blocked-1', PhysicalCondition.DAMAGED, OperationalStatus.BLOCKED, 90.0)
        result = self.service.compute_district_score(self.district)
        self.assertLess(result['score'], 5.0)

    def test_weather_penalty_extreme(self):
        """Extreme weather should apply maximum weather penalty."""
        _make_infra(self.district, 'Road-B', PhysicalCondition.GOOD, OperationalStatus.ACCESSIBLE, 10.0)
        _make_weather(self.district, WeatherCondition.EXTREME, 200.0)
        result = self.service.compute_district_score(self.district)
        weather_score = result['components']['weather_score']
        self.assertEqual(weather_score, 0.0)

    def test_empty_district_neutral_score(self):
        """District with no infrastructure returns neutral defaults, no crash."""
        result = self.service.compute_district_score(self.district)
        self.assertIsNotNone(result['score'])
        self.assertEqual(result['segment_count'], 0)

    def test_compute_all_districts_updates_db(self):
        """compute_all_districts() must update District.accessibility_score in DB."""
        _make_infra(self.district, 'Road-C')
        self.service.compute_all_districts()
        self.district.refresh_from_db()
        # score should have been written back
        self.assertIsNotNone(self.district.accessibility_score)

    def test_connectivity_status_reflected(self):
        """Critical connectivity_status should lower score vs normal."""
        _make_infra(self.district, 'Road-D', PhysicalCondition.GOOD, OperationalStatus.ACCESSIBLE, 5.0)
        _make_weather(self.district, WeatherCondition.CLEAR, 0.0)
        result_normal = self.service.compute_district_score(self.district)

        self.district.connectivity_status = ConnectivityStatus.CRITICAL
        self.district.save()
        result_critical = self.service.compute_district_score(self.district)
        self.assertLess(result_critical['score'], result_normal['score'])


class AccessibilityViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('accuser', password='pass')
        self.staff = User.objects.create_user('accstaff', password='pass', is_staff=True)
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff)
        self.district = District.objects.create(
            name='ViewDist', state='TestState', geom=_poly()
        )

    def test_get_district_accessibility_returns_breakdown(self):
        """GET district accessibility returns score breakdown."""
        resp = self.client_api.get(f'/api/v1/routes/districts/{self.district.pk}/accessibility/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('score', data)
        self.assertIn('components', data)
        self.assertIn('segment_count', data)

    def test_get_unknown_district_404(self):
        """GET unknown district_id returns 404."""
        resp = self.client_api.get('/api/v1/routes/districts/999999/accessibility/')
        self.assertEqual(resp.status_code, 404)

    def test_staff_can_trigger_refresh(self):
        """Staff POST to refresh endpoint triggers compute_all_districts."""
        resp = self.staff_client.post('/api/v1/routes/districts/accessibility/refresh/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('updated', data)

    def test_non_staff_refresh_rejected(self):
        """Non-staff user cannot trigger accessibility refresh."""
        resp = self.client_api.post('/api/v1/routes/districts/accessibility/refresh/')
        self.assertIn(resp.status_code, [401, 403])
