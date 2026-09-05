"""
Phase 5: End-to-End Intelligence Pipeline Tests.

Topology used (3 nodes, mirrors Phase 3 test pattern):
  P5_A ---[highway, NH-06]--- P5_B ---[connector]--- P5_C
  P5_A ----[bypass, SH-11, P5_A -> P5_C direct]----  P5_C

Incident on highway (P5_A->P5_B) spikes risk -> ranker prefers bypass (P5_A->P5_C).
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon, Point
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Role
from apps.reports.models import IncidentReport, IncidentType, SeverityLevel
from apps.reports.services.spatial_snap import snap
from apps.routes.models import (
    District,
    HazardLevel,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
)
from apps.routes.services.risk import RiskPredictionService
from apps.routes.services.routing.graph import RoadNetworkGraphService
from apps.routes.services.route_ranking import RouteRankingService
from apps.vehicles.services.eta import ETAEstimationService


class Phase5PipelineSetup(TestCase):
    """
    Base setUp: 3-node corridor so NetworkX generates two distinct paths.
      P5_A --[highway NH-06, 17km, high hazard]--> P5_B
      P5_B --[connector, 8km, low hazard]--> P5_C
      P5_A --[bypass SH-11, 30km, low hazard]--> P5_C  (direct alternate)
    """
    def setUp(self):
        self.client = APIClient()

        self.officer = User.objects.create_user(username="officer_p5", password="Password123!")
        self.officer.profile.role = Role.FIELD_OFFICER
        self.officer.profile.save()

        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name="P5 Kamrup",
            state="Assam",
            accessibility_score=9.0,
            geom=MultiPolygon(poly),
        )

        # P5_A -> P5_B: High hazard highway (will tip to HIGH after incident report)
        self.highway = Infrastructure.objects.create(
            district=self.district,
            name="P5 NH-06 Highway (A-B)",
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node="P5_A",
            end_node="P5_B",
            length_km=17.0,
            base_speed_kmh=50.0,
            landslide_susceptibility=HazardLevel.MEDIUM,
            flood_hazard_zone=HazardLevel.LOW,
            historical_landslide_count=1,
            recent_rainfall_mm=38.0,    # score=49.0 -> agg 41.65 < 45 -> shortest; after report +20=69.0 (HIGH) -> agg 58.65 >= 45 -> safe
            weather_warning=False,
            geom=LineString([(91.75, 26.18), (91.82, 26.13), (91.87, 26.10)]),
        )
        RiskPredictionService.assess_and_update(self.highway)

        # P5_B -> P5_C: Short connector
        self.connector = Infrastructure.objects.create(
            district=self.district,
            name="P5 Connector (B-C)",
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node="P5_B",
            end_node="P5_C",
            length_km=8.0,
            base_speed_kmh=50.0,
            landslide_susceptibility=HazardLevel.LOW,
            flood_hazard_zone=HazardLevel.LOW,
            historical_landslide_count=0,
            recent_rainfall_mm=0.0,
            weather_warning=False,
            geom=LineString([(91.87, 26.10), (91.90, 25.90), (91.88, 25.78)]),
        )
        RiskPredictionService.assess_and_update(self.connector)

        # P5_A -> P5_C: Low-risk bypass (direct, but longer)
        self.bypass = Infrastructure.objects.create(
            district=self.district,
            name="P5 SH-11 Safe Bypass (A-C)",
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.STATE_HIGHWAY,
            start_node="P5_A",
            end_node="P5_C",
            length_km=30.0,
            base_speed_kmh=40.0,
            landslide_susceptibility=HazardLevel.LOW,
            flood_hazard_zone=HazardLevel.LOW,
            historical_landslide_count=0,
            recent_rainfall_mm=0.0,
            weather_warning=False,
            geom=LineString([(91.75, 26.18), (91.95, 26.05), (91.88, 25.78)]),
        )
        RiskPredictionService.assess_and_update(self.bypass)


class PipelineUnitTests(Phase5PipelineSetup):

    def test_risk_rises_after_recent_incident_report(self):
        """Adding a critical incident report must increase the highway risk score."""
        self.highway.refresh_from_db()
        initial_score = self.highway.risk_score

        report = IncidentReport.objects.create(
            officer=self.officer,
            photo="reports/photos/p5_test/ph.jpg",
            location=Point(91.82, 26.13, srid=4326),
            description="Landslide on NH-06",
            incident_type=IncidentType.LANDSLIDE,
            severity=SeverityLevel.CRITICAL,
            client_timestamp=timezone.now(),
            ai_issue_type=IncidentType.LANDSLIDE,
            ai_severity=SeverityLevel.CRITICAL,
            ai_confidence=0.94,
            snapped_infrastructure=self.highway,
        )
        RiskPredictionService.assess_and_update(self.highway)
        self.highway.refresh_from_db()

        self.assertGreater(self.highway.risk_score, initial_score)
        self.assertIn("recent field incident report", self.highway.top_factors)
        report.delete()

    def test_spatial_snap_links_report_to_highway(self):
        """Report submitted near the highway LineString must snap to highway, not bypass."""
        report = IncidentReport.objects.create(
            officer=self.officer,
            photo="reports/photos/p5_test/ph.jpg",
            location=Point(91.82, 26.13, srid=4326),
            description="Test snap",
            incident_type=IncidentType.FLOOD,
            severity=SeverityLevel.HIGH,
            client_timestamp=timezone.now(),
            ai_issue_type=IncidentType.FLOOD,
            ai_severity=SeverityLevel.HIGH,
            ai_confidence=0.88,
        )
        snap(report)
        report.refresh_from_db()

        self.assertIsNotNone(report.snapped_infrastructure)
        self.assertEqual(report.snapped_infrastructure.pk, self.highway.pk)
        report.delete()

    def test_route_reranking_changes_recommendation_after_risk_spike(self):
        """
        Before incident: highway (P5_A->P5_B->P5_C) is recommended (shorter, acceptable risk).
        After critical landslide report -> highway risk spikes to HIGH -> bypass (P5_A->P5_C) recommended.
        """
        before_candidates = RoadNetworkGraphService.generate_candidate_routes("P5_A", "P5_C")
        before_ranked = RouteRankingService.rank_routes(before_candidates)
        before_rec = next(c for c in before_ranked if c.recommended)

        # Before: shortest route should be recommended (highway risk is MEDIUM)
        self.assertEqual(before_rec.route_id, "route-shortest")

        # Attach incident report to highway -> risk spikes to HIGH
        report = IncidentReport.objects.create(
            officer=self.officer,
            photo="reports/photos/p5_test/ph.jpg",
            location=Point(91.82, 26.13, srid=4326),
            description="Critical landslide",
            incident_type=IncidentType.LANDSLIDE,
            severity=SeverityLevel.CRITICAL,
            client_timestamp=timezone.now(),
            ai_issue_type=IncidentType.LANDSLIDE,
            ai_severity=SeverityLevel.CRITICAL,
            ai_confidence=0.95,
            snapped_infrastructure=self.highway,
        )
        RiskPredictionService.assess_and_update(self.highway)
        self.highway.refresh_from_db()

        after_candidates = RoadNetworkGraphService.generate_candidate_routes("P5_A", "P5_C")
        after_ranked = RouteRankingService.rank_routes(after_candidates)
        after_rec = next(c for c in after_ranked if c.recommended)

        # Highway must now be HIGH risk
        self.assertEqual(self.highway.risk_level, "high")
        # Recommended route must have changed to the safe bypass
        self.assertNotEqual(before_rec.route_id, after_rec.route_id)
        self.assertEqual(after_rec.route_id, "route-safe")
        self.assertIn("Recommended for safety", after_rec.explanation)

        report.delete()

    def test_eta_service_returns_delay_on_high_risk_route(self):
        """ETAEstimationService must return predicted_eta > base_eta for HIGH risk + heavy rain."""
        segments = [
            {
                "length_km": 20.0,
                "road_classification": "national_highway",
                "risk_score": 80.0,
                "status": "risky",
            }
        ]
        result = ETAEstimationService.calculate_eta_for_route(
            segments=segments,
            rainfall_mm=60.0,
            weather_warning=True,
        )

        self.assertGreater(result["predicted_eta_minutes"], result["base_eta_minutes"])
        self.assertGreater(result["expected_delay_minutes"], 0.0)
        self.assertIn(result["delay_severity"], ["minor", "moderate", "critical"])


class PipelineAPITests(Phase5PipelineSetup):

    def test_simulate_pipeline_endpoint_full_flow(self):
        """
        POST /api/v1/routes/simulate-pipeline/ must return 200, all five steps,
        before/after snapshots, ETA data, and recommendation_changed flag.
        """
        self.client.force_authenticate(user=self.officer)
        payload = {
            "incident_lat": 26.13,
            "incident_lng": 91.82,
            "incident_type": "landslide",
            "severity": "critical",
            "origin_node": "P5_A",
            "destination_node": "P5_C",
        }
        res = self.client.post("/api/v1/routes/simulate-pipeline/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        data = res.json()["data"]
        self.assertEqual(len(data["pipeline_steps"]), 5)
        self.assertIn("before", data)
        self.assertIn("after", data)
        self.assertIn("eta", data)
        self.assertIsNotNone(data["before"]["recommended_route"])
        self.assertIsNotNone(data["after"]["recommended_route"])
        self.assertIsNotNone(data["eta"])
        self.assertIn("base_eta_minutes", data["eta"])

    def test_simulate_pipeline_returns_400_for_missing_params(self):
        """Missing required params must return 400."""
        self.client.force_authenticate(user=self.officer)
        res = self.client.post("/api/v1/routes/simulate-pipeline/", {
            "incident_lat": 26.13,
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_simulate_pipeline_unauthenticated_rejected(self):
        """Unauthenticated request must return 401."""
        res = self.client.post("/api/v1/routes/simulate-pipeline/", {
            "incident_lat": 26.13,
            "incident_lng": 91.82,
            "origin_node": "P5_A",
            "destination_node": "P5_C",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
