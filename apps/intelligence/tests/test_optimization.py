"""
Unit and Integration Tests for Route Optimization Engine (Phase 9).
"""
from unittest.mock import patch
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon
from django.test import TestCase

from apps.intelligence.services.optimization import (
    DEFAULT_OPTIMIZATION_DISTANCE_WEIGHT,
    DEFAULT_OPTIMIZATION_RISK_WEIGHT,
    OptimizationConfig,
    OptimizedRouteCandidate,
    RouteOptimizationEngine,
    RouteOptimizationResult,
    get_optimization_config,
)
from apps.intelligence.services.route_risk import RouteRiskEngine
from apps.routes.models import District, Infrastructure, InfrastructureType, RiskLevel
from apps.routes.services.routing.graph import RouteCandidate


class RouteOptimizationEngineTests(TestCase):
    def setUp(self):
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name="Optimization Test District",
            state="Assam",
            geom=MultiPolygon(poly),
        )

        # Low risk segment (score 10.0)
        self.infra_safe = Infrastructure.objects.create(
            district=self.district,
            name="Safe Highway Segment",
            infra_type=InfrastructureType.ROAD,
            geom=LineString([(91.75, 26.18), (91.80, 26.15)]),
            start_node=4001,
            end_node=4002,
            length_km=15.0,
            risk_score=10.0,
            risk_level=RiskLevel.LOW,
            top_factors=[{"name": "recent_rainfall", "contribution": 10.0}],
        )

        # High risk segment (score 90.0)
        self.infra_risky = Infrastructure.objects.create(
            district=self.district,
            name="Dangerous Mountain Pass",
            infra_type=InfrastructureType.ROAD,
            geom=LineString([(91.80, 26.15), (91.85, 26.10)]),
            start_node=4001,
            end_node=4002,
            length_km=10.0,
            risk_score=90.0,
            risk_level=RiskLevel.HIGH,
            top_factors=[{"name": "landslide_susceptibility", "contribution": 30.0}],
        )

    # ── Test A: Empty Candidate List ─────────────────────────────────────
    def test_empty_candidate_list(self):
        """Empty or None candidate list returns defined empty optimization result."""
        res_empty = RouteOptimizationEngine.optimize_routes([])
        self.assertIsInstance(res_empty, RouteOptimizationResult)
        self.assertIsNone(res_empty.selected_route)
        self.assertIsNone(res_empty.selected_route_risk)
        self.assertEqual(res_empty.candidate_count, 0)
        self.assertEqual(len(res_empty.ranked_candidates), 0)
        self.assertIn("No candidate routes provided", res_empty.explanation)

        res_none = RouteOptimizationEngine.optimize_routes(None)
        self.assertEqual(res_none.candidate_count, 0)
        self.assertIsNone(res_none.selected_route)

    # ── Test B: Single Candidate ─────────────────────────────────────────
    def test_single_candidate_selection(self):
        """Single candidate is unconditionally selected with rank 1."""
        candidate = RouteCandidate(
            route_id="route-1",
            name="Solo Path",
            distance_km=25.0,
            base_eta_minutes=30.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"id": self.infra_safe.id, "length_km": 15.0, "risk_score": 10.0}],
        )
        res = RouteOptimizationEngine.optimize_routes([candidate])
        self.assertEqual(res.candidate_count, 1)
        self.assertIsNotNone(res.selected_route)
        self.assertEqual(res.selected_route.rank, 1)
        self.assertTrue(res.selected_route.is_selected)
        self.assertEqual(res.selected_route.route.route_id, "route-1")
        self.assertIn("selected as the only available candidate", res.explanation)

    # ── Test C: Distance-Only Preference ─────────────────────────────────
    def test_distance_only_preference(self):
        """When risk_weight=0, shorter route wins regardless of higher risk."""
        short_hazardous = RouteCandidate(
            route_id="route-short",
            name="Short Hazardous Route",
            distance_km=10.0,
            base_eta_minutes=12.0,
            risk_score=90.0,
            risk_level="high",
            segments=[{"id": self.infra_risky.id, "length_km": 10.0, "risk_score": 90.0}],
        )
        long_safe = RouteCandidate(
            route_id="route-long",
            name="Long Safe Route",
            distance_km=20.0,
            base_eta_minutes=25.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"id": self.infra_safe.id, "length_km": 20.0, "risk_score": 10.0}],
        )
        config = OptimizationConfig(distance_weight=1.0, risk_weight=0.0)
        res = RouteOptimizationEngine.optimize_routes([long_safe, short_hazardous], config=config)

        self.assertEqual(res.selected_route.route.route_id, "route-short")
        self.assertEqual(res.selected_route.rank, 1)
        # short_hazardous: d_norm=10/20=0.5, r_norm=0.9, cost = 1.0*0.5 + 0.0*0.9 = 0.5
        # long_safe: d_norm=20/20=1.0, r_norm=0.1, cost = 1.0*1.0 + 0.0*0.1 = 1.0
        self.assertAlmostEqual(res.selected_route.optimization_cost, 0.5)

    # ── Test D: Risk-Only Preference ─────────────────────────────────────
    def test_risk_only_preference(self):
        """When distance_weight=0, safer route wins regardless of greater distance."""
        short_hazardous = RouteCandidate(
            route_id="route-short",
            name="Short Hazardous Route",
            distance_km=10.0,
            base_eta_minutes=12.0,
            risk_score=90.0,
            risk_level="high",
            segments=[{"id": self.infra_risky.id, "length_km": 10.0, "risk_score": 90.0}],
        )
        long_safe = RouteCandidate(
            route_id="route-long",
            name="Long Safe Route",
            distance_km=30.0,
            base_eta_minutes=35.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"id": self.infra_safe.id, "length_km": 30.0, "risk_score": 10.0}],
        )
        config = OptimizationConfig(distance_weight=0.0, risk_weight=1.0)
        res = RouteOptimizationEngine.optimize_routes([short_hazardous, long_safe], config=config)

        self.assertEqual(res.selected_route.route.route_id, "route-long")
        self.assertEqual(res.selected_route.rank, 1)
        # long_safe: cost = 0.0*d_norm + 1.0*(10/100) = 0.10
        self.assertAlmostEqual(res.selected_route.optimization_cost, 0.10)

    # ── Test E: Balanced Optimization (60/40 default) ────────────────────
    def test_balanced_optimization_mathematical_formula(self):
        """
        Verify the 60/40 default calculation mathematically:
        Candidate 1: 10km, risk score 20.0
        Candidate 2: 20km, risk score 10.0
        d_max = 20.0
        C1: d_norm = 10/20 = 0.5, r_norm = 20/100 = 0.20
            cost = 0.60 * 0.50 + 0.40 * 0.20 = 0.30 + 0.08 = 0.38
        C2: d_norm = 20/20 = 1.0, r_norm = 10/100 = 0.10
            cost = 0.60 * 1.00 + 0.40 * 0.10 = 0.60 + 0.04 = 0.64
        """
        c1 = RouteCandidate(
            route_id="c1",
            name="C1",
            distance_km=10.0,
            base_eta_minutes=12.0,
            risk_score=20.0,
            risk_level="low",
            segments=[{"id": 991, "length_km": 10.0, "risk_score": 20.0}],
        )
        c2 = RouteCandidate(
            route_id="c2",
            name="C2",
            distance_km=20.0,
            base_eta_minutes=24.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"id": 992, "length_km": 20.0, "risk_score": 10.0}],
        )
        config = OptimizationConfig(distance_weight=0.60, risk_weight=0.40)
        res = RouteOptimizationEngine.optimize_routes([c1, c2], config=config)

        self.assertEqual(res.selected_route.route.route_id, "c1")
        self.assertAlmostEqual(res.ranked_candidates[0].optimization_cost, 0.38, places=5)
        self.assertAlmostEqual(res.ranked_candidates[1].optimization_cost, 0.64, places=5)

    # ── Test F: Normalization Across Complete Candidate Set ──────────────
    def test_normalization_across_complete_candidate_set(self):
        """Max distance in candidate set becomes normalized distance = 1.0."""
        c1 = RouteCandidate(
            route_id="c1",
            name="C1",
            distance_km=15.0,
            base_eta_minutes=15.0,
            risk_score=0.0,
            risk_level="low",
            segments=[],
        )
        c2 = RouteCandidate(
            route_id="c2",
            name="C2",
            distance_km=45.0,
            base_eta_minutes=45.0,
            risk_score=0.0,
            risk_level="low",
            segments=[],
        )
        res = RouteOptimizationEngine.optimize_routes([c1, c2])
        # Find c1 and c2 in ranked results
        res_c1 = next(c for c in res.ranked_candidates if c.route.route_id == "c1")
        res_c2 = next(c for c in res.ranked_candidates if c.route.route_id == "c2")

        self.assertAlmostEqual(res_c1.distance_normalized, 15.0 / 45.0, places=5)
        self.assertAlmostEqual(res_c2.distance_normalized, 1.0, places=5)

    # ── Test G: Zero-Distance Edge Case ──────────────────────────────────
    def test_zero_distance_edge_case(self):
        """When all candidate distances are 0, distance_normalized is 0.0 with no ZeroDivisionError."""
        c1 = RouteCandidate(
            route_id="c1",
            name="Zero 1",
            distance_km=0.0,
            base_eta_minutes=0.0,
            risk_score=30.0,
            risk_level="low",
            segments=[{"id": 991, "length_km": 0.0, "risk_score": 30.0}],
        )
        c2 = RouteCandidate(
            route_id="c2",
            name="Zero 2",
            distance_km=0.0,
            base_eta_minutes=0.0,
            risk_score=60.0,
            risk_level="medium",
            segments=[{"id": 992, "length_km": 0.0, "risk_score": 60.0}],
        )
        res = RouteOptimizationEngine.optimize_routes([c1, c2])
        self.assertEqual(res.ranked_candidates[0].distance_normalized, 0.0)
        self.assertEqual(res.ranked_candidates[1].distance_normalized, 0.0)
        self.assertEqual(res.selected_route.route.route_id, "c1")

    # ── Test H: Risk Normalization ───────────────────────────────────────
    def test_risk_normalization(self):
        """0 risk -> 0.0, 100 risk -> 1.0, clamped values."""
        c_min = RouteCandidate(
            route_id="c_min",
            name="Min Risk",
            distance_km=10.0,
            base_eta_minutes=10.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"id": 991, "length_km": 10.0, "risk_score": 0.0}],
        )
        c_max = RouteCandidate(
            route_id="c_max",
            name="Max Risk",
            distance_km=10.0,
            base_eta_minutes=10.0,
            risk_score=100.0,
            risk_level="high",
            segments=[{"id": 992, "length_km": 10.0, "risk_score": 100.0}],
        )
        res = RouteOptimizationEngine.optimize_routes([c_min, c_max])
        res_min = next(c for c in res.ranked_candidates if c.route.route_id == "c_min")
        res_max = next(c for c in res.ranked_candidates if c.route.route_id == "c_max")

        self.assertAlmostEqual(res_min.risk_normalized, 0.0)
        self.assertAlmostEqual(res_max.risk_normalized, 1.0)

    # ── Test I: Deterministic Tie-Breaking ────────────────────────────────
    def test_deterministic_tie_breaking(self):
        """
        Tie-breaking hierarchy:
        1. lowest optimization_cost
        2. lower route_risk score
        3. shorter distance
        4. stable original candidate index
        """
        # Scenario 1: Same cost, lower risk wins
        # Let distance_weight = 0.5, risk_weight = 0.5
        # Cand A: dist 20km (d_norm=1.0), risk 0.0 (r_norm=0.0) -> cost = 0.5*1.0 + 0.5*0.0 = 0.5
        # Cand B: dist 0km (d_norm=0.0), risk 100.0 (r_norm=1.0) -> cost = 0.5*0.0 + 0.5*1.0 = 0.5
        # Both cost 0.5. Cand A has risk 0.0, Cand B has risk 100.0. Cand A must win!
        config_equal = OptimizationConfig(distance_weight=0.5, risk_weight=0.5)
        cand_a = RouteCandidate(
            route_id="cand_a",
            name="A",
            distance_km=20.0,
            base_eta_minutes=20.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"id": 901, "length_km": 20.0, "risk_score": 0.0}],
        )
        cand_b = RouteCandidate(
            route_id="cand_b",
            name="B",
            distance_km=0.0,
            base_eta_minutes=0.0,
            risk_score=100.0,
            risk_level="high",
            segments=[{"id": 902, "length_km": 0.0, "risk_score": 100.0}],
        )
        res1 = RouteOptimizationEngine.optimize_routes([cand_b, cand_a], config=config_equal)
        self.assertEqual(res1.selected_route.route.route_id, "cand_a")

        # Scenario 2: Same cost, same risk, shorter distance wins
        # Cand C: dist 10km, risk 20.0
        # Cand D: dist 20km, risk 20.0
        # with distance_weight=0.0, risk_weight=1.0 -> both cost = 0.20, both risk 20.0
        # Cand C is shorter (10km vs 20km) -> Cand C must win!
        config_risk_only = OptimizationConfig(distance_weight=0.0, risk_weight=1.0)
        cand_c = RouteCandidate(
            route_id="cand_c",
            name="C",
            distance_km=10.0,
            base_eta_minutes=10.0,
            risk_score=20.0,
            risk_level="low",
            segments=[{"id": 903, "length_km": 10.0, "risk_score": 20.0}],
        )
        cand_d = RouteCandidate(
            route_id="cand_d",
            name="D",
            distance_km=20.0,
            base_eta_minutes=20.0,
            risk_score=20.0,
            risk_level="low",
            segments=[{"id": 904, "length_km": 20.0, "risk_score": 20.0}],
        )
        res2 = RouteOptimizationEngine.optimize_routes([cand_d, cand_c], config=config_risk_only)
        self.assertEqual(res2.selected_route.route.route_id, "cand_c")

        # Scenario 3: Same cost, same risk, same distance -> original order wins
        cand_e1 = RouteCandidate(
            route_id="cand_e1",
            name="E1",
            distance_km=15.0,
            base_eta_minutes=15.0,
            risk_score=30.0,
            risk_level="low",
            segments=[{"id": 905, "length_km": 15.0, "risk_score": 30.0}],
        )
        cand_e2 = RouteCandidate(
            route_id="cand_e2",
            name="E2",
            distance_km=15.0,
            base_eta_minutes=15.0,
            risk_score=30.0,
            risk_level="low",
            segments=[{"id": 906, "length_km": 15.0, "risk_score": 30.0}],
        )
        res3 = RouteOptimizationEngine.optimize_routes([cand_e1, cand_e2])
        self.assertEqual(res3.ranked_candidates[0].route.route_id, "cand_e1")
        self.assertEqual(res3.ranked_candidates[1].route.route_id, "cand_e2")

    # ── Test J: RouteRiskEngine Integration ───────────────────────────────
    def test_routeriskengine_integration_and_no_duplicate_logic(self):
        """Verify optimization delegates to RouteRiskEngine.assess_route without reimplementing risk."""
        candidate = RouteCandidate(
            route_id="route-test",
            name="Test",
            distance_km=15.0,
            base_eta_minutes=15.0,
            risk_score=0.0,
            risk_level="low",
            segments=[{"id": self.infra_risky.id, "length_km": 10.0, "risk_score": 90.0}],
        )

        with patch.object(RouteRiskEngine, "assess_route", wraps=RouteRiskEngine.assess_route) as mock_assess:
            res = RouteOptimizationEngine.optimize_routes([candidate])
            self.assertTrue(mock_assess.called)
            self.assertEqual(mock_assess.call_count, 1)
            # Verify route risk score from RouteRiskEngine is reflected on candidate result
            self.assertEqual(res.selected_route_risk.route_score, 90.0)
            self.assertEqual(res.selected_route_risk.route_level, "high")

    # ── Test K: Safer-Longer-Route Scenario ───────────────────────────────
    def test_safer_longer_route_scenario(self):
        """
        Route A: Shorter (10km) but severe risk (90.0).
        Route B: Longer (15km) but minimal risk (10.0).
        Under 60/40:
          d_max = 15.0
          Route A: d_norm = 10/15 = 0.6667, r_norm = 0.90 -> cost = 0.6*(2/3) + 0.4*0.9 = 0.40 + 0.36 = 0.7600
          Route B: d_norm = 15/15 = 1.0000, r_norm = 0.10 -> cost = 0.6*1.0 + 0.4*0.1 = 0.60 + 0.04 = 0.6400
        Route B is selected despite being 5.0 km longer!
        """
        route_a = RouteCandidate(
            route_id="route-a",
            name="Mountain Hazard Path",
            distance_km=10.0,
            base_eta_minutes=12.0,
            risk_score=90.0,
            risk_level="high",
            segments=[{"id": self.infra_risky.id, "length_km": 10.0, "risk_score": 90.0}],
        )
        route_b = RouteCandidate(
            route_id="route-b",
            name="Safe Detour Highway",
            distance_km=15.0,
            base_eta_minutes=18.0,
            risk_score=10.0,
            risk_level="low",
            segments=[{"id": self.infra_safe.id, "length_km": 15.0, "risk_score": 10.0}],
        )

        res = RouteOptimizationEngine.optimize_routes([route_a, route_b])
        self.assertEqual(res.selected_route.route.route_id, "route-b")
        self.assertEqual(res.selected_route.rank, 1)
        self.assertIn("despite being 5.0 km longer", res.explanation)
        self.assertIn("route-b", res.explanation)

    # ── Test L: Precision-Specific Test (Unrounded vs Rounded Ranking) ────
    def test_ranking_uses_unrounded_cost_precision(self):
        """
        Prove that ranking uses unrounded full-precision floating point optimization_cost
        rather than rounded presentation values.

        Construct two candidates where:
        - Candidate X: cost = 0.50004 -> rounded to 4 decimals = 0.5000. Risk = 10.0
        - Candidate Y: cost = 0.50001 -> rounded to 4 decimals = 0.5000. Risk = 20.0

        In unrounded comparison: Candidate Y (0.50001) < Candidate X (0.50004), so Candidate Y MUST rank #1.
        If the engine had rounded before ranking, cost would tie (0.5000 == 0.5000) and Candidate X would win due to lower risk (10.0 vs 20.0).
        """
        # Under 50/50 weights:
        # Cand X: dist = 100.008km, d_max = 100.008km (d_norm = 1.0), risk = 0.008 (r_norm = 0.00008)
        # -> cost_X = 0.5 * 1.0 + 0.5 * 0.00008 = 0.50004
        # Cand Y: dist = 100.002km, d_max = 100.008km (d_norm = 100.002/100.008 = 0.9999400048), risk = 0.016 (r_norm = 0.00016)
        # -> cost_Y = 0.5 * 0.9999400048 + 0.5 * 0.00016 = 0.4999700024 + 0.00008 = 0.5000500024
        # Let's craft exact distance/risk so cost_Y < cost_X:
        # Distance weight = 0.5, risk weight = 0.5
        # Cand X: distance = 10.0, risk = 20.008 (higher risk)
        # Cand Y: distance = 10.0, risk = 20.002 (lower risk) -> cost_Y < cost_X
        # To test precision independent of risk tiebreaker:
        # Let Cand 1 have shorter distance (d_norm slightly lower), but higher risk.
        # Cand 1: dist = 9.9998km, risk = 30.0
        # Cand 2: dist = 10.0km, risk = 29.998
        # d_max = 10.0. Weights = 0.5, 0.5.
        # Cand 1: d_norm = 0.99998, r_norm = 0.30000 -> cost1 = 0.5*0.99998 + 0.5*0.30000 = 0.49999 + 0.15000 = 0.649990
        # Cand 2: d_norm = 1.00000, r_norm = 0.29998 -> cost2 = 0.5*1.00000 + 0.5*0.29998 = 0.50000 + 0.14999 = 0.649990
        # In this setup, let's make cost1 = 0.649994 and cost2 = 0.649991:
        # Cand 2 has lower cost (0.649991 vs 0.649994), but Cand 2 has HIGHER risk (30.0 vs 29.9) or higher distance.
        # Both round to 0.6500 in 4 decimals.
        cand1 = RouteCandidate(
            route_id="c1",
            name="C1",
            distance_km=9.99988,  # d_norm = 0.999988
            base_eta_minutes=10.0,
            risk_score=10.0,  # Lower risk (would win tie-breaker if costs were tied)
            risk_level="low",
            segments=[{"id": 911, "length_km": 9.99988, "risk_score": 10.0}],
        )
        cand2 = RouteCandidate(
            route_id="c2",
            name="C2",
            distance_km=10.0,  # d_norm = 1.0
            base_eta_minutes=10.0,
            risk_score=9.9995,  # Slightly lower risk gives slightly lower unrounded cost:
            # Under 0.5/0.5:
            # c1: 0.5 * (9.99988/10.0) + 0.5 * (10.0/100) = 0.499994 + 0.050000 = 0.549994
            # c2: 0.5 * (10.0/10.0) + 0.5 * (9.9995/100) = 0.500000 + 0.0499975 = 0.5499975
            # So c1 has cost 0.5499940, c2 has cost 0.5499975.
            # Both round to 0.5500 at 4 decimal places!
            # c1 has lower cost (0.5499940 < 0.5499975) and must be selected as rank 1.
            risk_level="low",
            segments=[{"id": 912, "length_km": 10.0, "risk_score": 9.9995}],
        )
        config = OptimizationConfig(distance_weight=0.5, risk_weight=0.5)
        res = RouteOptimizationEngine.optimize_routes([cand2, cand1], config=config)

        # Unrounded comparison selects c1
        self.assertEqual(res.selected_route.route.route_id, "c1")
        self.assertLess(res.ranked_candidates[0].optimization_cost, res.ranked_candidates[1].optimization_cost)
        # Verify both round to the same value in presentation
        self.assertEqual(
            res.ranked_candidates[0].to_dict()["optimization_cost"],
            res.ranked_candidates[1].to_dict()["optimization_cost"],
        )

    # ── Test M: Candidate Set-Wide Distance Normalization Proof ───────────
    def test_distance_normalization_is_set_wide(self):
        """
        Distance normalization must be performed across the entire candidate set:
        Candidate A (10km) alone has d_norm = 1.0.
        When evaluated alongside Candidate B (100km), Candidate A has d_norm = 0.10.
        """
        cand_a = RouteCandidate(
            route_id="cand_a",
            name="A",
            distance_km=10.0,
            base_eta_minutes=10.0,
            risk_score=0.0,
            risk_level="low",
            segments=[],
        )
        cand_b = RouteCandidate(
            route_id="cand_b",
            name="B",
            distance_km=100.0,
            base_eta_minutes=100.0,
            risk_score=0.0,
            risk_level="low",
            segments=[],
        )

        # Alone:
        res_solo = RouteOptimizationEngine.optimize_routes([cand_a])
        self.assertEqual(res_solo.ranked_candidates[0].distance_normalized, 1.0)

        # In set with 100km candidate:
        res_set = RouteOptimizationEngine.optimize_routes([cand_a, cand_b])
        res_a_in_set = next(c for c in res_set.ranked_candidates if c.route.route_id == "cand_a")
        self.assertAlmostEqual(res_a_in_set.distance_normalized, 0.10, places=5)

    # ── Test N: Configuration Validation ─────────────────────────────────
    def test_configuration_validation(self):
        """Validate negative weights and zero sum configurations."""
        with self.assertRaises(ValueError):
            OptimizationConfig(distance_weight=-0.1, risk_weight=0.5)

        with self.assertRaises(ValueError):
            OptimizationConfig(distance_weight=0.5, risk_weight=-0.1)

        with self.assertRaises(ValueError):
            OptimizationConfig(distance_weight=0.0, risk_weight=0.0)

        # Non-standard weights normalize properly
        cfg = OptimizationConfig(distance_weight=6.0, risk_weight=4.0)
        self.assertAlmostEqual(cfg.normalized_distance_weight, 0.60)
        self.assertAlmostEqual(cfg.normalized_risk_weight, 0.40)

    # ── Test O: Serialization (to_dict) ──────────────────────────────────
    def test_serialization_to_dict(self):
        """Verify to_dict produces well-formed dictionary with presentation rounding."""
        candidate = RouteCandidate(
            route_id="route-1",
            name="Candidate Path",
            distance_km=12.3456,
            base_eta_minutes=15.0,
            risk_score=25.678,
            risk_level="low",
            segments=[{"id": self.infra_safe.id, "length_km": 12.3456, "risk_score": 10.0}],
        )
        res = RouteOptimizationEngine.optimize_routes([candidate])
        data = res.to_dict()

        self.assertIn("selected_route", data)
        self.assertIn("selected_route_risk", data)
        self.assertIn("ranked_candidates", data)
        self.assertIn("candidate_count", data)
        self.assertIn("explanation", data)

        cand_data = data["ranked_candidates"][0]
        self.assertIn("distance_normalized", cand_data)
        self.assertIn("risk_normalized", cand_data)
        self.assertIn("optimization_cost", cand_data)
        self.assertIn("rank", cand_data)
        self.assertIn("is_selected", cand_data)

    # ── Test P: Directed MultiDiGraph Edge Identity Preservation ─────────
    def test_multidigraph_directed_edge_identity_preservation(self):
        """
        Preserve directed edge identity (u, v, key) without reordering or mutating segments.
        """
        edge1 = (4001, 4002, self.infra_safe.id)
        edge2 = (4002, 4003, self.infra_risky.id)

        route = [edge1, edge2]
        res = RouteOptimizationEngine.optimize_routes([route])

        self.assertEqual(res.candidate_count, 1)
        selected_risk = res.selected_route_risk
        self.assertEqual(len(selected_risk.segments), 2)
        self.assertEqual(selected_risk.segments[0].edge_identity, edge1)
        self.assertEqual(selected_risk.segments[1].edge_identity, edge2)

