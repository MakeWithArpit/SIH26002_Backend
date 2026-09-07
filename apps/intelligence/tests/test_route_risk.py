"""
Unit and Integration Tests for Route Risk Engine (Phase 8).
"""
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon
from django.test import TestCase

from apps.intelligence.services.risk.config import RiskConfig
from apps.intelligence.services.route_risk import (
    FactorContributionSummary,
    RouteRiskEngine,
    RouteRiskResult,
    RouteSegmentRisk,
    calculate_length_weighted_score,
)
from apps.routes.models import (
    District,
    HazardLevel,
    Infrastructure,
    InfrastructureType,
    RiskLevel,
)
from apps.routes.services.routing.graph import RouteCandidate


class RouteRiskEngineTests(TestCase):
    def setUp(self):
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name="Route Risk Test District",
            state="Assam",
            geom=MultiPolygon(poly),
        )

        # Segment A: 10km, Low Risk (score: 10.0)
        self.infra_a = Infrastructure.objects.create(
            district=self.district,
            name="Highway Segment A",
            infra_type=InfrastructureType.ROAD,
            geom=LineString([(91.75, 26.18), (91.80, 26.15)]),
            start_node=3001,
            end_node=3002,
            length_km=10.0,
            risk_score=10.0,
            risk_level=RiskLevel.LOW,
            top_factors=[
                {"name": "landslide_susceptibility", "contribution": 0.0, "reason": "Low susceptibility"},
                {"name": "recent_rainfall", "contribution": 10.0, "reason": "Moderate rain"},
            ],
        )

        # Segment B: 30km, High Risk (score: 70.0)
        self.infra_b = Infrastructure.objects.create(
            district=self.district,
            name="Mountain Pass Segment B",
            infra_type=InfrastructureType.ROAD,
            geom=LineString([(91.80, 26.15), (91.85, 26.10)]),
            start_node=3002,
            end_node=3003,
            length_km=30.0,
            risk_score=70.0,
            risk_level=RiskLevel.HIGH,
            top_factors=[
                {"name": "landslide_susceptibility", "contribution": 30.0, "reason": "High susceptibility"},
                {"name": "historical_landslide", "contribution": 15.0, "reason": "2 historical incidents"},
                {"name": "recent_rainfall", "contribution": 25.0, "reason": "Heavy rain"},
            ],
        )

        # Segment C (Parallel to B): 30km, Low Risk (score: 0.0)
        self.infra_c = Infrastructure.objects.create(
            district=self.district,
            name="Detour Tunnel Segment C",
            infra_type=InfrastructureType.ROAD,
            geom=LineString([(91.80, 26.15), (91.85, 26.10)]),
            start_node=3002,
            end_node=3003,
            length_km=30.0,
            risk_score=0.0,
            risk_level=RiskLevel.LOW,
            top_factors=[],
        )

    # ── Test A: Empty Route ──────────────────────────────────────────────
    def test_empty_route_handling(self):
        """Empty route returns a safe/defined result without division-by-zero."""
        res = RouteRiskEngine.assess_route([])
        self.assertEqual(res.route_score, 0.0)
        self.assertEqual(res.route_level, "low")
        self.assertEqual(res.segment_count, 0)
        self.assertEqual(res.total_length_km, 0.0)
        self.assertEqual(len(res.segments), 0)
        self.assertIn("Empty route", res.explanation)

        res_none = RouteRiskEngine.assess_route(None)
        self.assertEqual(res_none.route_score, 0.0)

    # ── Test B: Single-Segment Route ─────────────────────────────────────
    def test_single_segment_route(self):
        """Single-segment route score equals infrastructure score."""
        res = RouteRiskEngine.assess_route([self.infra_a])
        self.assertEqual(res.route_score, 10.0)
        self.assertEqual(res.route_level, "low")
        self.assertEqual(res.segment_count, 1)
        self.assertEqual(res.total_length_km, 10.0)
        self.assertEqual(res.max_segment_score, 10.0)
        self.assertEqual(len(res.highest_risk_segments), 1)
        self.assertEqual(res.highest_risk_segments[0].infrastructure_id, self.infra_a.id)

    # ── Test C: Length-Weighted Aggregation ──────────────────────────────
    def test_length_weighted_aggregation_formula(self):
        """
        Verify length-weighted score mathematically:
        Segment A: 10km, score 10.0
        Segment B: 30km, score 70.0
        Weighted sum: (10 * 10.0) + (30 * 70.0) = 100 + 2100 = 2200
        Total length: 10 + 30 = 40km
        Route score = 2200 / 40 = 55.0
        """
        res = RouteRiskEngine.assess_route([self.infra_a, self.infra_b])
        self.assertEqual(res.route_score, 55.0)
        self.assertEqual(res.route_level, "medium")  # 40 <= 55 <= 69
        self.assertEqual(res.total_length_km, 40.0)
        self.assertEqual(res.segment_count, 2)
        self.assertEqual(res.high_risk_segment_count, 1)
        self.assertEqual(res.low_risk_segment_count, 1)

    # ── Test D: Missing Segment Length (Arithmetic Fallback) ─────────────
    def test_missing_length_fallback_to_arithmetic_mean(self):
        """
        When lengths are 0.0 or unavailable, falls back to arithmetic mean:
        seg1: score 30.0, length 0
        seg2: score 70.0, length 0
        Expected = (30.0 + 70.0) / 2 = 50.0
        """
        seg1 = RouteSegmentRisk(infrastructure_id=1, name="S1", length_km=0.0, risk_score=30.0)
        seg2 = RouteSegmentRisk(infrastructure_id=2, name="S2", length_km=0.0, risk_score=70.0)

        score = calculate_length_weighted_score([seg1, seg2])
        self.assertEqual(score, 50.0)

    # ── Test E: Risk Thresholds & Levels ─────────────────────────────────
    def test_route_risk_level_thresholds(self):
        """
        Verify route risk classification against canonical thresholds:
        0–39 LOW, 40–69 MEDIUM, 70–100 HIGH.
        """
        # Low route (e.g. 30.0)
        res_low = RouteRiskEngine.assess_route([self.infra_a])
        self.assertEqual(res_low.route_level, "low")

        # Medium route (55.0)
        res_med = RouteRiskEngine.assess_route([self.infra_a, self.infra_b])
        self.assertEqual(res_med.route_level, "medium")

        # High route (70.0)
        res_high = RouteRiskEngine.assess_route([self.infra_b])
        self.assertEqual(res_high.route_level, "high")

    # ── Test F: High-Risk Segment Identification ─────────────────────────
    def test_highest_risk_segment_identification(self):
        """Identifies peak risk segment(s) and reports max_segment_score."""
        res = RouteRiskEngine.assess_route([self.infra_a, self.infra_b])
        self.assertEqual(res.max_segment_score, 70.0)
        self.assertEqual(len(res.highest_risk_segments), 1)
        self.assertEqual(res.highest_risk_segments[0].infrastructure_id, self.infra_b.id)
        self.assertEqual(res.highest_risk_segments[0].name, "Mountain Pass Segment B")

    # ── Test G: Directed MultiDiGraph Edge Identity (u, v, key) ──────────
    def test_multigraph_directed_edge_identity(self):
        """
        Directed edge identity (u, v, key) must be preserved.
        Parallel edges between same nodes (3002, 3003) with distinct keys (infra_b.id vs infra_c.id)
        must not be conflated.
        """
        edge_b = (3002, 3003, self.infra_b.id)
        edge_c = (3002, 3003, self.infra_c.id)

        # Assess path with high-risk parallel edge B
        res_b = RouteRiskEngine.assess_route([(3001, 3002, self.infra_a.id), edge_b])
        self.assertEqual(res_b.route_score, 55.0)
        self.assertEqual(res_b.segments[1].edge_identity, edge_b)
        self.assertEqual(res_b.segments[1].risk_score, 70.0)

        # Assess path with safe parallel edge C
        res_c = RouteRiskEngine.assess_route([(3001, 3002, self.infra_a.id), edge_c])
        # (10*10 + 30*0)/40 = 100/40 = 2.5
        self.assertEqual(res_c.route_score, 2.5)
        self.assertEqual(res_c.segments[1].edge_identity, edge_c)
        self.assertEqual(res_c.segments[1].risk_score, 0.0)

    # ── Test H: Infrastructure Resolution ────────────────────────────────
    def test_infrastructure_mapping_and_factor_reading(self):
        """Resolves Infrastructure records and reads persisted factors correctly."""
        res = RouteRiskEngine.assess_route([self.infra_b.id])
        self.assertEqual(len(res.segments), 1)
        seg = res.segments[0]
        self.assertEqual(seg.infrastructure_id, self.infra_b.id)
        self.assertEqual(seg.risk_score, 70.0)
        self.assertEqual(seg.risk_level, "high")
        self.assertEqual(len(seg.top_factors), 3)

    # ── Test I: Factor Aggregation ───────────────────────────────────────
    def test_factor_contribution_aggregation(self):
        """
        Aggregates factor contributions across segments cleanly:
        - landslide_susceptibility: 30.0 from seg B (1 segment)
        - historical_landslide: 15.0 from seg B (1 segment)
        - recent_rainfall: 10.0 (seg A) + 25.0 (seg B) = 35.0 (2 segments)
        """
        res = RouteRiskEngine.assess_route([self.infra_a, self.infra_b])
        factor_map = {f.factor_name: f for f in res.factor_summary}

        self.assertIn("landslide_susceptibility", factor_map)
        self.assertEqual(factor_map["landslide_susceptibility"].total_contribution, 30.0)
        self.assertEqual(factor_map["landslide_susceptibility"].affected_segments_count, 1)

        self.assertIn("recent_rainfall", factor_map)
        self.assertEqual(factor_map["recent_rainfall"].total_contribution, 35.0)
        self.assertEqual(factor_map["recent_rainfall"].affected_segments_count, 2)
        self.assertEqual(factor_map["recent_rainfall"].max_single_contribution, 25.0)

    # ── Test J: Score Clamping ───────────────────────────────────────────
    def test_score_clamping_to_100(self):
        """Verify route score is clamped within [0, 100]."""
        extreme_seg = RouteSegmentRisk(infrastructure_id=99, name="Extreme", length_km=10.0, risk_score=150.0)
        score = calculate_length_weighted_score([extreme_seg])
        self.assertEqual(score, 100.0)

    # ── Test K: RouteCandidate Object Support ────────────────────────────
    def test_route_candidate_object_evaluation(self):
        """RouteCandidate instances can be passed directly to RouteRiskEngine."""
        candidate = RouteCandidate(
            route_id="route-1",
            name="Candidate Path",
            distance_km=40.0,
            base_eta_minutes=45.0,
            risk_score=0.0,
            risk_level="low",
            segments=[
                {"id": self.infra_a.id, "length_km": 10.0, "risk_score": 10.0},
                {"id": self.infra_b.id, "length_km": 30.0, "risk_score": 70.0},
            ],
        )

        res = RouteRiskEngine.assess_route(candidate)
        self.assertEqual(res.route_score, 55.0)
        self.assertEqual(res.route_level, "medium")
        self.assertEqual(res.segment_count, 2)
        self.assertTrue(len(res.explanation) > 0)
        self.assertIsInstance(res.to_dict(), dict)
