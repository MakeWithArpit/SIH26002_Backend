"""
Unit and Integration Tests for apps.intelligence Risk Engine.
"""
from io import StringIO
from unittest.mock import MagicMock
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.routes.models import (
    District,
    HazardLevel,
    Infrastructure,
    InfrastructureType,
    RiskLevel,
    WeatherCondition,
    WeatherSnapshot,
)
from apps.intelligence.services.risk import (
    RiskConfig,
    RiskEngine,
    RiskAssessmentResult,
    FactorAssessment,
    get_risk_config,
)


class RiskEngineTests(TestCase):
    def setUp(self):
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name="Intelligence Test District",
            state="Assam",
            geom=MultiPolygon(poly),
            accessibility_score=8.5,
        )

        self.infra = Infrastructure.objects.create(
            district=self.district,
            name="Intelligence Test Road",
            infra_type=InfrastructureType.ROAD,
            geom=LineString([(91.75, 26.18), (91.80, 26.15)]),
            start_node=2001,
            end_node=2002,
            length_km=12.0,
            landslide_susceptibility=HazardLevel.LOW,
            historical_landslide_count=0,
            landslide_nearby_count=0,
        )

    def _create_weather_snapshot(self, rainfall_mm: float, warning: bool = False) -> WeatherSnapshot:
        return WeatherSnapshot.objects.create(
            district=self.district,
            rainfall_mm=rainfall_mm,
            condition=WeatherCondition.CLEAR,
            weather_warning=warning,
            recorded_at=timezone.now(),
        )

    def test_zero_risk_segment(self):
        """Low susceptibility, 0 historical, rain <= 20mm -> score = 0.0, level = 'low'."""
        self._create_weather_snapshot(rainfall_mm=10.0)
        self.infra.landslide_susceptibility = HazardLevel.LOW
        self.infra.historical_landslide_count = 0
        self.infra.save()

        res = RiskEngine.assess(self.infra)
        self.assertEqual(res.score, 0.0)
        self.assertEqual(res.level, "low")
        for f in res.factors:
            self.assertEqual(f.contribution, 0.0)

    def test_high_susceptibility_only(self):
        """High susceptibility adds exactly 30 points."""
        self._create_weather_snapshot(rainfall_mm=5.0)
        self.infra.landslide_susceptibility = HazardLevel.HIGH
        self.infra.historical_landslide_count = 0
        self.infra.save()

        res = RiskEngine.assess(self.infra)
        self.assertEqual(res.score, 30.0)
        self.assertEqual(res.level, "low")  # 30 <= 39

        susc_factor = next(f for f in res.factors if f.name == "landslide_susceptibility")
        self.assertEqual(susc_factor.contribution, 30.0)
        self.assertEqual(susc_factor.value, "high")

    def test_historical_landslide_only(self):
        """Historical landslide activity adds exactly 15 points."""
        self._create_weather_snapshot(rainfall_mm=0.0)
        self.infra.landslide_susceptibility = HazardLevel.LOW
        self.infra.historical_landslide_count = 3
        self.infra.save()

        res = RiskEngine.assess(self.infra)
        self.assertEqual(res.score, 15.0)
        self.assertEqual(res.level, "low")

        hist_factor = next(f for f in res.factors if f.name == "historical_landslide")
        self.assertEqual(hist_factor.contribution, 15.0)
        self.assertEqual(hist_factor.value, 3)

    def test_rainfall_at_or_below_20mm(self):
        """Rainfall <= 20mm contributes 0 points."""
        self._create_weather_snapshot(rainfall_mm=20.0)
        res = RiskEngine.assess(self.infra)
        rain_factor = next(f for f in res.factors if f.name == "recent_rainfall")
        self.assertEqual(rain_factor.contribution, 0.0)
        self.assertEqual(rain_factor.value, 20.0)

    def test_rainfall_proportional_between_20_and_50(self):
        """Rainfall between 20 and 50mm contributes proportionally: ((35-20)/(50-20))*25 = 12.5."""
        self._create_weather_snapshot(rainfall_mm=35.0)
        res = RiskEngine.assess(self.infra)
        rain_factor = next(f for f in res.factors if f.name == "recent_rainfall")
        self.assertAlmostEqual(rain_factor.contribution, 12.5, places=1)
        self.assertEqual(rain_factor.value, 35.0)

    def test_rainfall_at_or_above_50mm(self):
        """Rainfall >= 50mm contributes maximum heavy rainfall weight (25.0)."""
        self._create_weather_snapshot(rainfall_mm=65.0)
        res = RiskEngine.assess(self.infra)
        rain_factor = next(f for f in res.factors if f.name == "recent_rainfall")
        self.assertEqual(rain_factor.contribution, 25.0)
        self.assertEqual(rain_factor.value, 65.0)

    def test_combined_score(self):
        """High susceptibility (30) + Historical (15) + Rain >= 50 (25) = 70.0 (HIGH)."""
        self._create_weather_snapshot(rainfall_mm=55.0)
        self.infra.landslide_susceptibility = HazardLevel.HIGH
        self.infra.historical_landslide_count = 2
        self.infra.save()

        res = RiskEngine.assess(self.infra)
        self.assertEqual(res.score, 70.0)
        self.assertEqual(res.level, "high")

    def test_risk_threshold_boundaries(self):
        """Test exact risk level boundaries: 0-39 LOW, 40-69 MEDIUM, 70-100 HIGH."""
        cfg = get_risk_config()
        self.assertEqual(RiskEngine.classify_risk_level(0.0, cfg), "low")
        self.assertEqual(RiskEngine.classify_risk_level(39.0, cfg), "low")
        self.assertEqual(RiskEngine.classify_risk_level(39.1, cfg), "medium")
        self.assertEqual(RiskEngine.classify_risk_level(40.0, cfg), "medium")
        self.assertEqual(RiskEngine.classify_risk_level(69.0, cfg), "medium")
        self.assertEqual(RiskEngine.classify_risk_level(69.1, cfg), "high")
        self.assertEqual(RiskEngine.classify_risk_level(70.0, cfg), "high")
        self.assertEqual(RiskEngine.classify_risk_level(100.0, cfg), "high")

    def test_score_clamping(self):
        """Engine score is clamped to [0.0, 100.0] even with extreme configuration."""
        custom_cfg = RiskConfig(
            weight_landslide_susceptibility_high=60.0,
            weight_historical_landslide=50.0,
            weight_heavy_rainfall=50.0,
        )
        self._create_weather_snapshot(rainfall_mm=60.0)
        self.infra.landslide_susceptibility = HazardLevel.HIGH
        self.infra.historical_landslide_count = 5
        self.infra.save()

        res = RiskEngine.assess(self.infra, config=custom_cfg)
        self.assertEqual(res.score, 100.0)
        self.assertEqual(res.level, "high")

    def test_missing_weather_snapshot(self):
        """When no weather snapshot exists, rainfall contributes 0 and provides explicit reason."""
        # Note: No WeatherSnapshot created for self.district
        res = RiskEngine.assess(self.infra)
        self.assertEqual(res.score, 0.0)
        rain_factor = next(f for f in res.factors if f.name == "recent_rainfall")
        self.assertEqual(rain_factor.contribution, 0.0)
        self.assertIsNone(rain_factor.value)
        self.assertIn("Weather data unavailable", rain_factor.reason)

    def test_missing_static_enrichment(self):
        """Missing or null susceptibility / historical count defaults safely to 0."""
        self._create_weather_snapshot(rainfall_mm=10.0)
        self.infra.landslide_susceptibility = ""
        self.infra.historical_landslide_count = 0
        self.infra.landslide_nearby_count = 0
        self.infra.save()

        res = RiskEngine.assess(self.infra)
        self.assertEqual(res.score, 0.0)

    def test_flood_hazard_inactive(self):
        """Flood hazard remains strictly inactive (0.0 points) without fabricating signals."""
        self.infra.flood_hazard_zone = HazardLevel.HIGH
        self.infra.save()

        res = RiskEngine.assess(self.infra)
        flood_factor = next(f for f in res.factors if f.name == "flood_hazard")
        self.assertEqual(flood_factor.contribution, 0.0)
        self.assertIsNone(flood_factor.value)
        self.assertIn("inactive", flood_factor.reason.lower())

    def test_weather_warning_inactive(self):
        """Official weather warning remains inactive (0.0 points) pending real warning source."""
        self._create_weather_snapshot(rainfall_mm=10.0, warning=True)
        res = RiskEngine.assess(self.infra)
        warn_factor = next(f for f in res.factors if f.name == "weather_warning")
        self.assertEqual(warn_factor.contribution, 0.0)
        self.assertIsNone(warn_factor.value)
        self.assertIn("inactive", warn_factor.reason.lower())

    def test_deterministic_repeated_calculation(self):
        """Running assess multiple times produces strictly identical results."""
        self._create_weather_snapshot(rainfall_mm=40.0)
        self.infra.landslide_susceptibility = HazardLevel.HIGH
        self.infra.historical_landslide_count = 1
        self.infra.save()

        res1 = RiskEngine.assess(self.infra)
        res2 = RiskEngine.assess(self.infra)
        self.assertEqual(res1.score, res2.score)
        self.assertEqual(res1.level, res2.level)
        self.assertEqual(len(res1.factors), len(res2.factors))
        for f1, f2 in zip(res1.factors, res2.factors):
            self.assertEqual(f1.name, f2.name)
            self.assertEqual(f1.contribution, f2.contribution)

    def test_persistence(self):
        """assess_and_update persists risk_score, risk_level, risk_updated_at, top_factors."""
        self._create_weather_snapshot(rainfall_mm=55.0)
        self.infra.landslide_susceptibility = HazardLevel.HIGH
        self.infra.historical_landslide_count = 2
        self.infra.save()

        before_update = timezone.now()
        updated = RiskEngine.assess_and_update(self.infra)

        self.assertEqual(updated.risk_score, 70.0)
        self.assertEqual(updated.risk_level, "high")
        self.assertIsNotNone(updated.risk_updated_at)
        self.assertGreaterEqual(updated.risk_updated_at, before_update)
        self.assertTrue(len(updated.top_factors) > 0)

        # Reload from database to verify persistence
        self.infra.refresh_from_db()
        self.assertEqual(self.infra.risk_score, 70.0)
        self.assertEqual(self.infra.risk_level, "high")
        self.assertIsNotNone(self.infra.risk_updated_at)
        self.assertEqual(len(self.infra.top_factors), 5)

    def test_batch_processing(self):
        """assess_and_update_batch successfully evaluates and updates multiple segments."""
        infra2 = Infrastructure.objects.create(
            district=self.district,
            name="Road 2",
            infra_type=InfrastructureType.ROAD,
            geom=LineString([(91.70, 26.10), (91.75, 26.15)]),
            start_node=2003,
            end_node=2004,
            length_km=5.0,
            landslide_susceptibility=HazardLevel.HIGH,
        )
        self._create_weather_snapshot(rainfall_mm=25.0)

        successful, errors = RiskEngine.assess_and_update_batch([self.infra, infra2])
        self.assertEqual(len(successful), 2)
        self.assertEqual(len(errors), 0)

        self.infra.refresh_from_db()
        infra2.refresh_from_db()
        self.assertIsNotNone(self.infra.risk_updated_at)
        self.assertIsNotNone(infra2.risk_updated_at)

    def test_partial_failure_isolation(self):
        """An error on one item does not prevent other items from being processed."""
        broken_infra = MagicMock()
        broken_infra.id = 9999
        broken_infra.name = "Broken Infra"
        broken_infra.landslide_susceptibility = "low"
        broken_infra.historical_landslide_count = 0
        broken_infra.landslide_nearby_count = 0
        broken_infra.district = self.district
        broken_infra.save.side_effect = RuntimeError("Database lock error")

        successful, errors = RiskEngine.assess_and_update_batch([broken_infra, self.infra])
        self.assertEqual(len(successful), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(successful[0].id, self.infra.id)
        self.assertEqual(errors[0][0], broken_infra)
        self.assertIsInstance(errors[0][1], RuntimeError)

    def test_management_command_dry_run(self):
        """calculate_risk --dry-run prints output without updating DB records."""
        out = StringIO()
        call_command("calculate_risk", dry_run=True, stdout=out)
        output = out.getvalue()
        self.assertIn("DRY-RUN", output)
        self.assertIn("Risk Calculation Summary", output)

        self.infra.refresh_from_db()
        self.assertIsNone(self.infra.risk_updated_at)

    def test_management_command_single_infrastructure(self):
        """calculate_risk --infrastructure <id> evaluates only that specific segment."""
        out = StringIO()
        call_command("calculate_risk", infrastructure=self.infra.id, stdout=out)
        output = out.getvalue()
        self.assertIn(f"[{self.infra.id}", output)
        self.assertIn("Targeting 1 segment(s)", output)

        self.infra.refresh_from_db()
        self.assertIsNotNone(self.infra.risk_updated_at)

    def test_management_command_invalid_infrastructure(self):
        """calculate_risk with non-existent id raises CommandError."""
        with self.assertRaises(CommandError):
            call_command("calculate_risk", infrastructure=999999)
