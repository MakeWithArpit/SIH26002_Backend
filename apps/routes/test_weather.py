"""
Comprehensive tests for Dynamic Weather Ingestion (Phase 6).

Covers:
- A. OpenMeteoProvider HTTP normalization, validation, timeout, and failure handling
- B. Rainfall aggregation (24-hour hourly sum, safe null handling, non-current hour logic)
- C. WMO code to condition deterministic mapping
- D. District point-on-surface coordinate derivation and district association
- E. WeatherSnapshot persistence and historical preservation
- F. Partial failure and graceful degradation across multiple districts
- G. Management command (sync_weather) options: all, single district, dry-run
- H. Read-only API endpoint (/api/v1/routes/districts/{id}/weather/)
"""
from datetime import datetime
import json
from unittest.mock import MagicMock, patch
import zoneinfo

from django.contrib.auth.models import User
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
import requests

from apps.accounts.models import Role
from apps.routes.models import District, WeatherCondition, WeatherSnapshot
from apps.routes.services.weather.base import WeatherData, WeatherProvider
from apps.routes.services.weather.exceptions import (
    WeatherAPIError,
    WeatherProviderError,
    WeatherTimeoutError,
    WeatherValidationError,
)
from apps.routes.services.weather.mock import MockWeatherProvider
from apps.routes.services.weather.open_meteo import OpenMeteoProvider
from apps.routes.services.weather.service import WeatherService
from apps.routes.services.weather.wmo import WMO_CODE_MAP, wmo_code_to_condition


def make_mock_open_meteo_payload(
    current_time: str = "2026-09-07T14:30",
    weather_code: int = 61,
    temp: float = 24.5,
    humidity: float = 88.0,
    wind: float = 12.4,
    hourly_rain_values: list = None,
    tz_name: str = "Asia/Kolkata",
) -> dict:
    """Helper creating a valid mock Open-Meteo response dictionary."""
    if hourly_rain_values is None:
        # 24 hours of 1.0 mm = 24.0 mm
        hourly_rain_values = [1.0] * 24

    # Generate 24 hourly timestamps matching the rain count
    base_dt = datetime.fromisoformat(current_time)
    hourly_times = []
    for i in range(len(hourly_rain_values) - 1, -1, -1):
        dt = base_dt - timezone.timedelta(hours=i)
        hourly_times.append(dt.strftime("%Y-%m-%dT%H:00"))

    return {
        "latitude": 26.15,
        "longitude": 91.77,
        "timezone": tz_name,
        "timezone_offset_seconds": 19800,
        "current": {
            "time": current_time,
            "interval": 900,
            "temperature_2m": temp,
            "relative_humidity_2m": humidity,
            "precipitation": 2.5,
            "rain": 2.5,
            "weather_code": weather_code,
            "wind_speed_10m": wind,
        },
        "hourly": {
            "time": hourly_times,
            "rain": hourly_rain_values,
            "precipitation": hourly_rain_values,
            "weather_code": [weather_code] * len(hourly_rain_values),
            "temperature_2m": [temp] * len(hourly_rain_values),
            "relative_humidity_2m": [humidity] * len(hourly_rain_values),
            "wind_speed_10m": [wind] * len(hourly_rain_values),
        },
    }


class WeatherProviderTests(TestCase):
    """Test Suite A: Provider HTTP, normalization, validation, timeout, and failure handling."""

    def setUp(self):
        self.provider = OpenMeteoProvider(
            base_url="https://api.open-meteo.com/v1/forecast",
            timeout_seconds=5.0,
            recent_hours=24,
        )

    @patch("requests.get")
    def test_valid_open_meteo_normalization(self, mock_get):
        """Valid response is parsed into WeatherData with correct fields and types."""
        raw_payload = make_mock_open_meteo_payload(
            current_time="2026-09-07T12:00",
            weather_code=65,  # heavy rain
            temp=22.0,
            humidity=95.0,
            wind=15.0,
            hourly_rain_values=[2.0] * 24,  # sum = 48.0 mm
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = raw_payload
        mock_get.return_value = mock_resp

        weather = self.provider.fetch_weather(26.15, 91.77)

        self.assertIsInstance(weather, WeatherData)
        self.assertEqual(weather.rainfall_mm, 48.0)
        self.assertEqual(weather.condition, WeatherCondition.HEAVY)
        self.assertEqual(weather.temperature_c, 22.0)
        self.assertEqual(weather.humidity_pct, 95.0)
        self.assertEqual(weather.wind_speed_kmh, 15.0)
        self.assertFalse(weather.weather_warning)  # WMO code is NOT a government warning
        self.assertIsNotNone(weather.recorded_at.tzinfo)
        self.assertEqual(weather.raw_payload, raw_payload)

    @patch("requests.get")
    def test_http_failure_raises_weather_api_error(self, mock_get):
        """Non-200 HTTP status raises typed WeatherAPIError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_get.return_value = mock_resp

        with self.assertRaises(WeatherAPIError) as ctx:
            self.provider.fetch_weather(26.15, 91.77)
        self.assertEqual(ctx.exception.status_code, 503)

    @patch("requests.get")
    def test_timeout_raises_weather_timeout_error(self, mock_get):
        """Connection timeout raises typed WeatherTimeoutError."""
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        with self.assertRaises(WeatherTimeoutError):
            self.provider.fetch_weather(26.15, 91.77)

    @patch("requests.get")
    def test_network_failure_raises_weather_api_error(self, mock_get):
        """General requests exception raises typed WeatherAPIError."""
        mock_get.side_effect = requests.exceptions.ConnectionError("DNS failure")

        with self.assertRaises(WeatherAPIError):
            self.provider.fetch_weather(26.15, 91.77)

    @patch("requests.get")
    def test_malformed_json_raises_validation_error(self, mock_get):
        """Missing required current/hourly blocks raises WeatherValidationError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": True, "reason": "No data"}
        mock_get.return_value = mock_resp

        with self.assertRaises(WeatherValidationError):
            self.provider.fetch_weather(26.15, 91.77)

    def test_coordinates_out_of_bounds_raises_validation_error(self):
        """Invalid lat/lng values raise WeatherValidationError immediately."""
        with self.assertRaises(WeatherValidationError):
            self.provider.fetch_weather(95.0, 91.77)

        with self.assertRaises(WeatherValidationError):
            self.provider.fetch_weather(26.15, 190.0)


class RainfallAggregationTests(TestCase):
    """Test Suite B: 24-hour rainfall summation, safe nulls, and non-current hour logic."""

    def setUp(self):
        self.provider = OpenMeteoProvider()

    def test_previous_24h_rainfall_summation(self):
        """Sums exactly the previous 24 hourly rain records."""
        # 24 hours with variable rain: 0.5 * 10 + 2.0 * 14 = 5.0 + 28.0 = 33.0 mm
        hourly_rains = [0.5] * 10 + [2.0] * 14
        payload = make_mock_open_meteo_payload(hourly_rain_values=hourly_rains)

        weather = self.provider.normalize_payload(payload, 26.15, 91.77)
        self.assertEqual(weather.rainfall_mm, 33.0)

    def test_current_hour_value_not_used_alone(self):
        """The calculation must not simply echo current.rain."""
        # current.rain is 10.0, but hourly past 24h sum is 2.5
        payload = make_mock_open_meteo_payload(hourly_rain_values=[0.1] * 24 + [0.1])
        payload["current"]["rain"] = 10.0

        weather = self.provider.normalize_payload(payload, 26.15, 91.77)
        # Should sum hourly values (~2.4 mm), NOT 10.0
        self.assertNotEqual(weather.rainfall_mm, 10.0)
        self.assertEqual(weather.rainfall_mm, 2.4)

    def test_null_and_none_hourly_values_handled_safely(self):
        """Null values in hourly rain array are safely treated as 0.0."""
        hourly_rains = [None, 1.5, None, 2.5] + [None] * 20
        payload = make_mock_open_meteo_payload(hourly_rain_values=hourly_rains)

        weather = self.provider.normalize_payload(payload, 26.15, 91.77)
        self.assertEqual(weather.rainfall_mm, 4.0)

    def test_negative_hourly_rain_raises_validation_error(self):
        """Negative rainfall data raises WeatherValidationError rather than corrupting DB."""
        hourly_rains = [1.0] * 23 + [-5.0]
        payload = make_mock_open_meteo_payload(hourly_rain_values=hourly_rains)

        with self.assertRaises(WeatherValidationError):
            self.provider.normalize_payload(payload, 26.15, 91.77)


class WeatherConditionMappingTests(TestCase):
    """Test Suite C: Deterministic WMO weather code mapping."""

    def test_wmo_code_mapping_determinism(self):
        """Test representative WMO codes mapping to clear, moderate, heavy, extreme."""
        # Clear
        self.assertEqual(wmo_code_to_condition(0), WeatherCondition.CLEAR)
        self.assertEqual(wmo_code_to_condition(1), WeatherCondition.CLEAR)
        self.assertEqual(wmo_code_to_condition(2), WeatherCondition.CLEAR)
        self.assertEqual(wmo_code_to_condition(3), WeatherCondition.CLEAR)

        # Moderate
        self.assertEqual(wmo_code_to_condition(45), WeatherCondition.MODERATE)  # Fog
        self.assertEqual(wmo_code_to_condition(51), WeatherCondition.MODERATE)  # Light Drizzle
        self.assertEqual(wmo_code_to_condition(61), WeatherCondition.MODERATE)  # Slight Rain
        self.assertEqual(wmo_code_to_condition(63), WeatherCondition.MODERATE)  # Moderate Rain
        self.assertEqual(wmo_code_to_condition(80), WeatherCondition.MODERATE)  # Slight Showers

        # Heavy
        self.assertEqual(wmo_code_to_condition(65), WeatherCondition.HEAVY)     # Heavy Rain
        self.assertEqual(wmo_code_to_condition(67), WeatherCondition.HEAVY)     # Heavy Freezing Rain
        self.assertEqual(wmo_code_to_condition(82), WeatherCondition.HEAVY)     # Violent Showers
        self.assertEqual(wmo_code_to_condition(95), WeatherCondition.HEAVY)     # Thunderstorm

        # Extreme
        self.assertEqual(wmo_code_to_condition(96), WeatherCondition.EXTREME)   # Thunderstorm with Hail
        self.assertEqual(wmo_code_to_condition(99), WeatherCondition.EXTREME)   # Severe Hail Thunderstorm

    def test_all_defined_wmo_codes_map_to_valid_choices(self):
        """Every code in the map resolves to a valid WeatherCondition choice."""
        valid_choices = [c[0] for c in WeatherCondition.choices]
        for code, condition in WMO_CODE_MAP.items():
            self.assertIn(condition, valid_choices, f"Code {code} mapped to invalid choice '{condition}'")


class WeatherServiceIntegrationTests(TestCase):
    """Test Suites D, E, F: District coordinates, WeatherSnapshot persistence, and partial failure isolation."""

    def setUp(self):
        # District A (Kamrup polygon)
        poly_a = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district_a = District.objects.create(
            name="District Alpha",
            state="Assam",
            accessibility_score=8.5,
            geom=MultiPolygon(poly_a),
        )

        # District B (Ri-Bhoi polygon)
        poly_b = Polygon(((91.80, 25.75), (92.05, 25.75), (92.05, 25.95), (91.80, 25.95), (91.80, 25.75)))
        self.district_b = District.objects.create(
            name="District Beta",
            state="Meghalaya",
            accessibility_score=7.0,
            geom=MultiPolygon(poly_b),
        )

    def test_district_point_on_surface_derivation(self):
        """Test Suite D: Derives a valid coordinate pair guaranteed to lie within district boundary."""
        lat, lng = WeatherService.resolve_district_coordinates(self.district_a)
        self.assertTrue(26.05 <= lat <= 26.25)
        self.assertTrue(91.60 <= lng <= 91.95)

    def test_successful_synchronization_creates_weathersnapshot(self):
        """Test Suite E: Synchronizing creates a persisted WeatherSnapshot associated with district."""
        mock_provider = MockWeatherProvider(
            rainfall_mm=14.2,
            condition=WeatherCondition.HEAVY,
            temperature_c=21.0,
            humidity_pct=90.0,
            wind_speed_kmh=18.5,
        )

        snapshot = WeatherService.sync_district(self.district_a, provider=mock_provider)

        self.assertIsNotNone(snapshot.id)
        self.assertEqual(snapshot.district, self.district_a)
        self.assertEqual(snapshot.rainfall_mm, 14.2)
        self.assertEqual(snapshot.condition, WeatherCondition.HEAVY)
        self.assertEqual(snapshot.temperature_c, 21.0)
        self.assertEqual(snapshot.humidity_pct, 90.0)
        self.assertEqual(snapshot.wind_speed_kmh, 18.5)
        self.assertFalse(snapshot.weather_warning)

        # Verify query on district
        self.assertEqual(self.district_a.weather_snapshots.count(), 1)
        self.assertEqual(self.district_a.latest_weather, snapshot)

    def test_repeat_synchronization_creates_historical_records(self):
        """Test Suite E: Subsequent syncs create new historical records rather than overwriting."""
        provider = MockWeatherProvider(rainfall_mm=5.0)
        snap1 = WeatherService.sync_district(self.district_a, provider=provider)

        provider.rainfall_mm = 12.0
        snap2 = WeatherService.sync_district(self.district_a, provider=provider)

        self.assertEqual(self.district_a.weather_snapshots.count(), 2)
        self.assertNotEqual(snap1.id, snap2.id)
        self.assertEqual(self.district_a.latest_weather.rainfall_mm, 12.0)

    def test_partial_failure_isolation_across_districts(self):
        """Test Suite F: If district B fails, district A succeeds, B's last snapshot survives, C executes."""
        # Pre-seed District B with a valid initial snapshot
        initial_snap_b = WeatherSnapshot.objects.create(
            district=self.district_b,
            rainfall_mm=8.0,
            condition=WeatherCondition.CLEAR,
            recorded_at=timezone.now(),
        )

        # Custom provider that fails ONLY on District B coordinates
        class SelectiveFailingProvider(WeatherProvider):
            def fetch_weather(self, lat: float, lng: float) -> WeatherData:
                # District B latitude is ~25.85
                if 25.75 <= lat <= 25.95:
                    raise WeatherAPIError("Open-Meteo HTTP 500 for District B")
                return WeatherData(
                    rainfall_mm=10.0,
                    condition=WeatherCondition.MODERATE,
                    recorded_at=timezone.now(),
                )

        result = WeatherService.sync_all_districts(
            districts=[self.district_a, self.district_b],
            provider=SelectiveFailingProvider(),
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["successful_count"], 1)
        self.assertEqual(result["failed_count"], 1)

        # District A succeeded
        self.assertEqual(self.district_a.weather_snapshots.count(), 1)
        # District B failed, but retained its previous snapshot
        self.district_b.refresh_from_db()
        self.assertEqual(self.district_b.weather_snapshots.count(), 1)
        self.assertEqual(self.district_b.latest_weather, initial_snap_b)
        self.assertEqual(self.district_b.latest_weather.rainfall_mm, 8.0)


class ManagementCommandTests(TestCase):
    """Test Suite G: sync_weather management command options."""

    def setUp(self):
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name="Command Test District",
            state="Assam",
            geom=MultiPolygon(poly),
        )

    def test_dry_run_does_not_persist(self):
        """--dry-run fetches and displays data without saving to the database."""
        call_command("sync_weather", dry_run=True, provider="mock")
        self.assertEqual(WeatherSnapshot.objects.count(), 0)

    def test_sync_weather_single_district(self):
        """--district filters synchronization to the specified district."""
        call_command("sync_weather", district=str(self.district.id), provider="mock")
        self.assertEqual(self.district.weather_snapshots.count(), 1)


class WeatherAPITests(TestCase):
    """Test Suite H: Read-only GET /api/v1/routes/districts/{id}/weather/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="weather_user", password="Password123!")
        self.user.profile.role = Role.NORMAL_USER
        self.user.profile.save()

        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name="API Weather District",
            state="Assam",
            geom=MultiPolygon(poly),
        )

    def test_unauthenticated_request_rejected(self):
        """Endpoint requires authentication."""
        resp = self.client.get(f"/api/v1/routes/districts/{self.district.id}/weather/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_district_without_weather_returns_null_data(self):
        """Returns 200 with empty data dict when no snapshots exist yet."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.get(f"/api/v1/routes/districts/{self.district.id}/weather/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"], {})

    def test_district_with_weather_returns_latest_snapshot(self):
        """Returns latest successful WeatherSnapshot."""
        self.client.force_authenticate(user=self.user)

        # Create older and newer snapshots
        WeatherSnapshot.objects.create(
            district=self.district,
            rainfall_mm=5.0,
            condition=WeatherCondition.CLEAR,
            recorded_at=timezone.now() - timezone.timedelta(hours=2),
        )
        latest = WeatherSnapshot.objects.create(
            district=self.district,
            rainfall_mm=18.5,
            condition=WeatherCondition.HEAVY,
            temperature_c=23.4,
            humidity_pct=92.0,
            wind_speed_kmh=14.0,
            recorded_at=timezone.now(),
        )

        resp = self.client.get(f"/api/v1/routes/districts/{self.district.id}/weather/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        res_data = resp.json()["data"]

        self.assertEqual(res_data["district"], self.district.id)
        self.assertEqual(res_data["district_name"], self.district.name)
        self.assertEqual(res_data["rainfall_mm"], 18.5)
        self.assertEqual(res_data["condition"], WeatherCondition.HEAVY)
        self.assertEqual(res_data["temperature_c"], 23.4)
        self.assertEqual(res_data["humidity_pct"], 92.0)
        self.assertEqual(res_data["wind_speed_kmh"], 14.0)
        self.assertFalse(res_data["weather_warning"])
