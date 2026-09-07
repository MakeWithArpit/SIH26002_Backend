"""
Comprehensive Unit and Integration Tests for ETA Estimation Engine (Phase 10).

Covers Suites A through M + constraint validations:
- A. Empty / invalid route handling
- B. Single route with no conditions (adjusted ETA == base ETA)
- C. Distance and base ETA calculation
- D. High-risk segment adjustment (clamped multipliers, road status)
- E. Weather severity adjustment (heavy rain, moderate rain, IMD warning)
- F. Combined conditions (multi-factor delay composition)
- G. No double-counting of route risk (single canonical assessment path)
- H. Zero and very small route distance handling
- I. Deterministic repeated calculation
- J. Timezone-aware absolute ETA (UTC and Asia/Kolkata)
- K. Missing weather snapshot / unavailable dynamic conditions
- L. Serialization and dictionary contract
- M. Existing ETA / Trip regression compatibility
- Constraints: No external weather HTTP requests, Trip schema validation.
"""
from datetime import datetime, timezone as dt_timezone, timedelta
from unittest.mock import MagicMock, patch
import zoneinfo

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from apps.intelligence.services.eta.config import (
    ETAConfig,
    get_eta_config,
    DEFAULT_ROAD_CLASS_SPEEDS,
)
from apps.intelligence.services.eta.engine import ETAEngine
from apps.intelligence.services.eta.result import ETAFactorAdjustment, ETAResult
from apps.intelligence.services.optimization.result import OptimizedRouteCandidate
from apps.intelligence.services.route_risk.engine import RouteRiskEngine
from apps.intelligence.services.route_risk.result import RouteRiskResult, RouteSegmentRisk
from apps.routes.models import District, Infrastructure, WeatherCondition, WeatherSnapshot
from apps.routes.services.routing.graph import RouteCandidate
from apps.vehicles.models import Trip, TripStatus, Vehicle, VehicleType
from apps.vehicles.services.eta import ETAEstimationService


class ETATestBase(TestCase):
    def setUp(self):
        self.config = ETAConfig()


class TestSuiteAEmptyInvalidRoute(ETATestBase):
    """Test Suite A: Empty / invalid route handling."""

    def test_none_candidate(self):
        result = ETAEngine.estimate_eta(None, config=self.config)
        self.assertEqual(result.distance_km, 0.0)
        self.assertEqual(result.base_eta_minutes, 0.0)
        self.assertEqual(result.adjusted_eta_minutes, 0.0)
        self.assertEqual(result.expected_delay_minutes, 0.0)
        self.assertEqual(result.delay_severity, "none")
        self.assertIn("No navigable route segments", result.explanation)

    def test_empty_segments_candidate(self):
        candidate = RouteCandidate(
            route_id="route-empty",
            name="Empty Route",
            distance_km=0.0,
            base_eta_minutes=0.0,
            risk_score=0.0,
            risk_level="low",
            segments=[],
        )
        result = ETAEngine.estimate_eta(candidate, config=self.config)
        self.assertEqual(result.adjusted_eta_minutes, 0.0)
        self.assertEqual(result.expected_delay_minutes, 0.0)

    def test_empty_dict_candidate(self):
        result = ETAEngine.estimate_eta({'segments': []}, config=self.config)
        self.assertEqual(result.adjusted_eta_minutes, 0.0)


class TestSuiteBSingleRouteNoConditions(ETATestBase):
    """Test Suite B: Single route with no conditions (adjusted ETA == base ETA)."""

    def test_ideal_conditions_match_base_eta(self):
        candidate = RouteCandidate(
            route_id="route-ideal",
            name="Ideal Highway Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=10.0,
            risk_level="low",
            segments=[
                {
                    "name": "Highway Section 1",
                    "length_km": 50.0,
                    "road_classification": "national_highway",
                    "base_speed_kmh": 50.0,
                    "risk_score": 10.0,
                    "status": "accessible",
                }
            ],
        )

        result = ETAEngine.estimate_eta(candidate, config=self.config)
        self.assertEqual(result.base_eta_minutes, 60.0)
        self.assertEqual(result.adjusted_eta_minutes, 60.0)
        self.assertEqual(result.expected_delay_minutes, 0.0)
        self.assertEqual(result.delay_severity, "none")
        self.assertEqual(len(result.adjustments), 0)
        self.assertIn("optimal", result.explanation)


class TestSuiteCDistanceAndBaseETACalculation(ETATestBase):
    """Test Suite C: Distance and base ETA calculation from road classifications."""

    def test_segment_classification_speeds(self):
        # 50km on NH (50 km/h) = 60 min
        # 20km on SH (40 km/h) = 30 min
        # 15km on MDR (30 km/h) = 30 min
        # 5km on Rural (25 km/h) = 12 min
        # Total distance = 90 km, Total base time = 132 min
        segments = [
            {"name": "NH Segment", "length_km": 50.0, "road_classification": "national_highway"},
            {"name": "SH Segment", "length_km": 20.0, "road_classification": "state_highway"},
            {"name": "MDR Segment", "length_km": 15.0, "road_classification": "major_district_road"},
            {"name": "Rural Segment", "length_km": 5.0, "road_classification": "rural_road"},
        ]
        result = ETAEngine.estimate_eta({"segments": segments}, config=self.config)
        self.assertEqual(result.distance_km, 90.0)
        self.assertAlmostEqual(result.base_eta_minutes, 132.0, places=1)


class TestSuiteDHighRiskSegmentAdjustment(ETATestBase):
    """Test Suite D: High-risk segment adjustments and blocked status."""

    def test_high_risk_segment_slowdown(self):
        # 50 km on NH -> 60 min base. Risk score = 85.0 (High >= 70)
        # Normalized excess: (85 - 70) / (100 - 70) = 0.5
        # Multiplier: 1.40 + (0.5 * 0.35) = 1.575
        # Delay: 60 * 0.575 = 34.5 min
        candidate = RouteCandidate(
            route_id="route-hazardous",
            name="Hazardous Mountain Pass",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=85.0,
            risk_level="high",
            segments=[
                {
                    "name": "Mountain Pass",
                    "length_km": 50.0,
                    "road_classification": "national_highway",
                    "risk_score": 85.0,
                    "status": "accessible",
                }
            ],
        )
        result = ETAEngine.estimate_eta(candidate, config=self.config)
        self.assertEqual(result.base_eta_minutes, 60.0)
        self.assertAlmostEqual(result.adjusted_eta_minutes, 94.5, places=1)
        self.assertAlmostEqual(result.expected_delay_minutes, 34.5, places=1)
        self.assertEqual(result.delay_severity, "moderate")
        self.assertTrue(any(a.category == "segment_risk" for a in result.adjustments))

    def test_blocked_segment_delay(self):
        # Blocked segment gets +120 min delay
        segments = [
            {
                "name": "Landslide Sector",
                "length_km": 10.0,
                "road_classification": "national_highway",
                "risk_score": 90.0,
                "status": "blocked",
            }
        ]
        result = ETAEngine.estimate_eta({"segments": segments}, config=self.config)
        self.assertAlmostEqual(result.expected_delay_minutes, 120.0, places=1)
        self.assertEqual(result.delay_severity, "critical")
        self.assertTrue(any(a.category == "blocked" for a in result.adjustments))


class TestSuiteEWeatherSeverityAdjustment(ETATestBase):
    """Test Suite E: Weather severity adjustments."""

    def test_heavy_rainfall_delay(self):
        # Base time 60 min. Heavy rain (60mm >= 50mm) -> +25% = +15 min
        candidate = RouteCandidate(
            route_id="route-rain",
            name="Rainy Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"name": "Sector A", "length_km": 50.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, rainfall_mm=60.0, config=self.config)
        self.assertEqual(result.base_eta_minutes, 60.0)
        self.assertAlmostEqual(result.adjusted_eta_minutes, 75.0, places=1)
        self.assertAlmostEqual(result.expected_delay_minutes, 15.0, places=1)
        self.assertEqual(result.delay_severity, "minor")
        self.assertTrue(any(a.category == "weather_severity" for a in result.adjustments))

    def test_moderate_rainfall_delay(self):
        # Base time 60 min. Moderate rain (30mm >= 20mm) -> +12% = +7.2 min
        candidate = RouteCandidate(
            route_id="route-mod-rain",
            name="Moderate Rain Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"name": "Sector A", "length_km": 50.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, rainfall_mm=30.0, config=self.config)
        self.assertAlmostEqual(result.expected_delay_minutes, 7.2, places=1)

    def test_weather_warning_delay(self):
        # Base time 60 min. Weather warning only -> +10% = +6.0 min
        candidate = RouteCandidate(
            route_id="route-warn",
            name="Advisory Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"name": "Sector A", "length_km": 50.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, weather_warning=True, config=self.config)
        self.assertAlmostEqual(result.expected_delay_minutes, 6.0, places=1)


class TestSuiteFCombinedConditions(ETATestBase):
    """Test Suite F: Combined risk and weather conditions."""

    def test_combined_high_risk_and_heavy_rain(self):
        # 50km on NH (60 min base).
        # Risk score 85 (delay 34.5 min).
        # Heavy rain (60mm -> +25% of 60 min = 15.0 min).
        # Total delay = 34.5 + 15.0 = 49.5 min -> critical severity (>=45 min)
        candidate = RouteCandidate(
            route_id="route-combined",
            name="Storm in Mountain Pass",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=85.0,
            risk_level="high",
            segments=[
                {
                    "name": "Pass",
                    "length_km": 50.0,
                    "road_classification": "national_highway",
                    "risk_score": 85.0,
                    "status": "accessible",
                }
            ],
        )
        result = ETAEngine.estimate_eta(candidate, rainfall_mm=60.0, config=self.config)
        self.assertAlmostEqual(result.adjusted_eta_minutes, 109.5, places=1)
        self.assertAlmostEqual(result.expected_delay_minutes, 49.5, places=1)
        self.assertEqual(result.delay_severity, "critical")
        self.assertEqual(len(result.adjustments), 2)


class TestSuiteGNoDoubleCountingRisk(ETATestBase):
    """Test Suite G: Validates single canonical risk input path without redundant assess_route calls."""

    def test_optimized_route_candidate_reuses_existing_route_risk(self):
        route_candidate = RouteCandidate(
            route_id="route-opt",
            name="Optimized Candidate",
            distance_km=40.0,
            base_eta_minutes=48.0,
            risk_score=20.0,
            risk_level="low",
            segments=[
                {
                    "name": "Plain Sector",
                    "length_km": 40.0,
                    "road_classification": "national_highway",
                    "risk_score": 20.0,
                }
            ],
        )
        precomputed_risk = RouteRiskResult(
            route_score=20.0,
            route_level="low",
            max_segment_score=20.0,
            highest_risk_segments=[],
            segment_count=1,
            high_risk_segment_count=0,
            medium_risk_segment_count=0,
            low_risk_segment_count=1,
            total_length_km=40.0,
            segments=[
                RouteSegmentRisk(
                    infrastructure_id=101,
                    name="Plain Sector",
                    length_km=40.0,
                    risk_score=20.0,
                    risk_level="low",
                )
            ],
            factor_summary=[],
            explanation="Low risk route",
        )
        optimized = OptimizedRouteCandidate(
            route=route_candidate,
            route_risk=precomputed_risk,
            distance_normalized=0.2,
            risk_normalized=0.2,
            optimization_cost=0.2,
            rank=1,
            is_selected=True,
        )

        with patch.object(RouteRiskEngine, "assess_route") as mock_assess:
            result = ETAEngine.estimate_eta(optimized, config=self.config)
            mock_assess.assert_not_called()
            self.assertEqual(result.base_eta_minutes, 48.0)


class TestSuiteHZeroSmallDistance(ETATestBase):
    """Test Suite H: Zero and very small route distance edge cases."""

    def test_zero_distance_no_crash(self):
        candidate = RouteCandidate(
            route_id="route-zero",
            name="Zero Distance",
            distance_km=0.0,
            base_eta_minutes=0.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"length_km": 0.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, config=self.config)
        self.assertEqual(result.adjusted_eta_minutes, 0.0)
        self.assertEqual(result.expected_delay_minutes, 0.0)

    def test_very_small_distance(self):
        candidate = RouteCandidate(
            route_id="route-micro",
            name="Micro Distance",
            distance_km=0.005,
            base_eta_minutes=0.006,
            risk_score=0.0,
            risk_level="low",
            segments=[{"length_km": 0.005, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, config=self.config)
        self.assertGreater(result.base_eta_minutes, 0.0)


class TestSuiteIDeterministicRepeatedCalculation(ETATestBase):
    """Test Suite I: Deterministic repeated calculation."""

    def test_identical_repeated_calls(self):
        candidate = RouteCandidate(
            route_id="route-rep",
            name="Repeat Route",
            distance_km=65.0,
            base_eta_minutes=78.0,
            risk_score=75.0,
            risk_level="high",
            segments=[
                {"name": "Sec 1", "length_km": 35.0, "road_classification": "national_highway", "risk_score": 75.0},
                {"name": "Sec 2", "length_km": 30.0, "road_classification": "state_highway", "risk_score": 45.0},
            ],
        )

        res1 = ETAEngine.estimate_eta(candidate, rainfall_mm=25.0, config=self.config)
        res2 = ETAEngine.estimate_eta(candidate, rainfall_mm=25.0, config=self.config)

        self.assertEqual(res1.adjusted_eta_minutes, res2.adjusted_eta_minutes)
        self.assertEqual(res1.expected_delay_minutes, res2.expected_delay_minutes)
        self.assertEqual(res1.explanation, res2.explanation)


class TestSuiteJTimezoneAwareAbsoluteETA(ETATestBase):
    """Test Suite J: Timezone-aware absolute ETA calculations."""

    def test_utc_timezone_preserved(self):
        start_utc = datetime(2026, 9, 7, 10, 0, 0, tzinfo=dt_timezone.utc)
        candidate = RouteCandidate(
            route_id="route-utc",
            name="UTC Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"length_km": 50.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, start_time=start_utc, config=self.config)
        self.assertIsNotNone(result.estimated_arrival_time)
        self.assertEqual(result.estimated_arrival_time.tzinfo, dt_timezone.utc)
        self.assertEqual(result.estimated_arrival_time, start_utc + timedelta(minutes=60))

    def test_kolkata_timezone_preserved(self):
        tz_kolkata = zoneinfo.ZoneInfo("Asia/Kolkata")
        start_ist = datetime(2026, 9, 7, 15, 30, 0, tzinfo=tz_kolkata)
        candidate = RouteCandidate(
            route_id="route-ist",
            name="IST Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"length_km": 50.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, start_time=start_ist, config=self.config)
        self.assertIsNotNone(result.estimated_arrival_time)
        self.assertEqual(result.estimated_arrival_time.tzinfo, tz_kolkata)
        self.assertEqual(result.estimated_arrival_time, start_ist + timedelta(minutes=60))


class TestSuiteKMissingWeatherSnapshot(ETATestBase):
    """Test Suite K: Missing weather snapshot / dynamic conditions gracefully handled."""

    def test_none_weather_applies_zero_weather_delay(self):
        candidate = RouteCandidate(
            route_id="route-nowx",
            name="No Weather Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"length_km": 50.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(
            candidate,
            weather_snapshot=None,
            rainfall_mm=None,
            weather_warning=None,
            weather_condition=None,
            config=self.config,
        )
        self.assertEqual(result.adjusted_eta_minutes, 60.0)
        self.assertFalse(any(a.category == "weather_severity" for a in result.adjustments))


class TestSuiteLSerialization(ETATestBase):
    """Test Suite L: Serialization to dictionary contract."""

    def test_to_dict_structure(self):
        start_time = datetime(2026, 9, 7, 12, 0, 0, tzinfo=dt_timezone.utc)
        candidate = RouteCandidate(
            route_id="route-ser",
            name="Serialization Route",
            distance_km=50.0,
            base_eta_minutes=60.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"length_km": 50.0, "road_classification": "national_highway"}],
        )
        result = ETAEngine.estimate_eta(candidate, start_time=start_time, config=self.config)
        d = result.to_dict()

        self.assertIn("route_id", d)
        self.assertIn("distance_km", d)
        self.assertIn("base_eta_minutes", d)
        self.assertIn("adjusted_eta_minutes", d)
        self.assertIn("expected_delay_minutes", d)
        self.assertIn("delay_severity", d)
        self.assertIn("start_time", d)
        self.assertIn("estimated_arrival_time", d)
        self.assertIn("adjustments", d)
        self.assertIn("top_factors", d)
        self.assertIn("explanation", d)
        self.assertEqual(d["start_time"], "2026-09-07T12:00:00+00:00")


class TestSuiteMTripAndVehiclesRegression(TestCase):
    """Test Suite M: Regression tests with Trip model and ETAEstimationService."""

    def setUp(self):
        self.user = User.objects.create_user(username="eta_driver", password="Password123!")
        self.vehicle = Vehicle.objects.create(
            registration_number="AS-01-ETA-9999",
            vehicle_type=VehicleType.TRUCK,
            current_speed=30.0,
        )
        self.trip = Trip.objects.create(
            trip_code="TRIP-ETA-TEST",
            vehicle=self.vehicle,
            driver=self.user,
            origin=Point(91.75, 26.18, srid=4326),
            origin_name="Guwahati Dispatch",
            destination=Point(91.88, 26.00, srid=4326),
            destination_name="Shillong Dropoff",
            status=TripStatus.ON_ROUTE,
        )

    def test_trip_schema_preserved(self):
        """Verify the exact Trip fields exist without any model alterations."""
        self.assertTrue(hasattr(self.trip, "base_eta_minutes"))
        self.assertTrue(hasattr(self.trip, "predicted_eta_minutes"))
        self.assertTrue(hasattr(self.trip, "expected_delay_minutes"))
        self.assertTrue(hasattr(self.trip, "eta_factors"))
        self.assertTrue(hasattr(self.trip, "last_eta_updated_at"))

    def test_update_trip_eta_facade(self):
        """Verify ETAEstimationService updates Trip instance correctly."""
        segments = [
            {
                "name": "NH-06 Section 1",
                "length_km": 30.0,
                "road_classification": "national_highway",
                "risk_score": 85.0,
                "status": "risky",
            }
        ]
        updated_trip = ETAEstimationService.update_trip_eta(self.trip, segments=segments)
        self.assertGreater(updated_trip.base_eta_minutes, 0.0)
        self.assertGreater(updated_trip.predicted_eta_minutes, updated_trip.base_eta_minutes)
        self.assertGreater(updated_trip.expected_delay_minutes, 0.0)
        self.assertTrue(len(updated_trip.eta_factors) > 0)

    def test_no_external_weather_http_requests(self):
        """Verify ETAEngine never triggers external HTTP requests."""
        candidate = RouteCandidate(
            route_id="route-no-http",
            name="No HTTP Route",
            distance_km=25.0,
            base_eta_minutes=30.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"length_km": 25.0, "road_classification": "national_highway"}],
        )
        with patch("requests.get") as mock_get:
            ETAEngine.estimate_eta(candidate)
            mock_get.assert_not_called()

