from django.test import TestCase
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon
from rest_framework.test import APIClient
from rest_framework import status
import json

from apps.routes.models import (
    District,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
    WeatherSnapshot,
    HazardLevel,
)
from apps.routes.services.routing.graph import RoadNetworkGraphService


class EndToEndPipelineTests(TestCase):
    """
    Phase 11: E2E Pipeline Validation.
    Proves the full pipeline (Graph -> Risk -> Optimization -> ETA) works continuously
    as a coherent system, and accurately responds to changing environmental conditions.
    """

    def setUp(self):
        RoadNetworkGraphService.clear_graph_cache()
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name='Kamrup',
            state='Assam',
            accessibility_score=9.0,
            geom=MultiPolygon(poly),
        )

        # Base Weather: Clear, 0mm rain
        from django.utils import timezone
        self.weather = WeatherSnapshot.objects.create(
            district=self.district,
            rainfall_mm=0.0,
            condition='clear',
            weather_warning=False,
            recorded_at=timezone.now(),
        )

        self.node_a = 101
        self.node_b = 102
        self.node_c = 103

        # Primary Highway: Direct A->C (15 km)
        # Low risk by default.
        self.infra_ac = Infrastructure.objects.create(
            district=self.district, name='Primary Highway A-C', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=self.node_a, end_node=self.node_c, oneway=False,
            length_km=15.0, base_speed_kmh=50.0, geom=LineString([(0, 0), (2, 2)]),
            landslide_susceptibility=HazardLevel.LOW,
            historical_landslide_count=0
        )

        # Bypass Route: A->B->C (25 km total)
        # Even longer, but extremely safe.
        self.infra_ab = Infrastructure.objects.create(
            district=self.district, name='Bypass Segment A-B', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.STATE_HIGHWAY,
            start_node=self.node_a, end_node=self.node_b, oneway=False,
            length_km=10.0, base_speed_kmh=40.0, geom=LineString([(0, 0), (1, 1)]),
            landslide_susceptibility=HazardLevel.LOW,
            historical_landslide_count=0
        )

        self.infra_bc = Infrastructure.objects.create(
            district=self.district, name='Bypass Segment B-C', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.STATE_HIGHWAY,
            start_node=self.node_b, end_node=self.node_c, oneway=False,
            length_km=15.0, base_speed_kmh=40.0, geom=LineString([(1, 1), (2, 2)]),
            landslide_susceptibility=HazardLevel.LOW,
            historical_landslide_count=0
        )

        self.client = APIClient()
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='e2e_user', password='Password123!')
        self.client.force_authenticate(user=self.user)

    def test_pipeline_baseline_then_adverse_condition(self):
        """
        Tests the pipeline end-to-end:
        1. Baseline: Clear weather. Shortest route (A-C) should be selected.
        2. Adverse: Heavy rainfall + static hazard on A-C.
           Risk should increase, ETA should delay.
           The recommendation might switch, or stay the same depending on normalized cost math.
        """
        payload = {
            "origin_node": str(self.node_a),
            "destination_node": str(self.node_c)
        }

        # ---------------------------------------------------------
        # SCENARIO A: BASELINE (Clear Weather)
        # ---------------------------------------------------------
        response_baseline = self.client.post('/api/v1/routes/calculate/', payload, format='json')
        self.assertEqual(response_baseline.status_code, 200)
        
        data_base = response_baseline.json()['data']
        routes_base = data_base['routes']
        self.assertEqual(len(routes_base), 2)  # Direct A-C, and Bypass A-B-C

        recommended_base = next(r for r in routes_base if r['recommended'])
        self.assertEqual(recommended_base['distance_km'], 15.0)  # Direct route selected
        self.assertLess(recommended_base['risk_score'], 40.0) # Should be low risk
        
        base_eta = recommended_base['base_eta_minutes']
        adjusted_eta = recommended_base['adjusted_eta_minutes']
        self.assertAlmostEqual(base_eta, adjusted_eta, places=1) # No delays
        self.assertEqual(recommended_base['delay_severity'], 'none')

        # ---------------------------------------------------------
        # SCENARIO B: ADVERSE CONDITIONS
        # ---------------------------------------------------------
        # 1. We introduce heavy rainfall to the district.
        self.weather.rainfall_mm = 85.0
        self.weather.condition = 'heavy'
        self.weather.weather_warning = True
        self.weather.save()

        # 2. We expose that the Primary Highway actually has high landslide susceptibility.
        self.infra_ac.landslide_susceptibility = HazardLevel.HIGH
        self.infra_ac.historical_landslide_count = 3
        self.infra_ac.save()
        
        # 3. We must force the RiskEngine to re-evaluate the infrastructure before calculating routes.
        # In a real system this happens via async tasks or batch jobs.
        from apps.intelligence.services.risk.engine import RiskEngine
        RiskEngine.assess_and_update(self.infra_ac)
        RiskEngine.assess_and_update(self.infra_ab)
        RiskEngine.assess_and_update(self.infra_bc)
        
        # We need to reload graph cache because edge properties like 'status' or weights might be cached
        RoadNetworkGraphService.clear_graph_cache()

        response_adverse = self.client.post('/api/v1/routes/calculate/', payload, format='json')
        self.assertEqual(response_adverse.status_code, 200)
        
        data_adv = response_adverse.json()['data']
        routes_adv = data_adv['routes']
        
        recommended_adv = next(r for r in routes_adv if r['recommended'])
        not_recommended_adv = next(r for r in routes_adv if not r['recommended'])

        print("\n--- E2E PIPELINE REPORT: BASELINE vs ADVERSE ---")
        print(f"BASELINE: Recommended Route Distance: {recommended_base['distance_km']}km, Risk: {recommended_base['risk_score']}")
        print(f"ADVERSE: Recommended Route Distance: {recommended_adv['distance_km']}km, Risk: {recommended_adv['risk_score']}")
        print(f"ADVERSE: Alternative Route Distance: {not_recommended_adv['distance_km']}km, Risk: {not_recommended_adv['risk_score']}")
        
        # Identify the direct route in adverse conditions
        direct_adv = next(r for r in routes_adv if r['distance_km'] == 15.0)
        
        # We verify that Risk increased significantly on the direct route
        self.assertGreater(direct_adv['risk_score'], recommended_base['risk_score'])
        self.assertEqual(direct_adv['risk_level'], 'high')
        
        # We verify that ETA delays were applied
        self.assertGreater(direct_adv['adjusted_eta_minutes'], direct_adv['base_eta_minutes'])
        
        # Has the recommendation changed? We print the mathematical breakdown
        if recommended_adv['distance_km'] != 15.0:
            print("-> Switch occurred! The safe bypass was mathematically optimal due to high risk on the direct route.")
        else:
            print("-> NO Switch occurred. The bypass distance/cost was too prohibitive to justify the detour despite the risk.")
            print("Explanation:", recommended_adv['explanation'])
            
        print("ETA Top Factors:", recommended_adv.get('top_factors', []))
        print("--------------------------------------------------\n")

    def test_missing_weather_handled_gracefully(self):
        """
        Ensures that if WeatherSnapshot is missing/stale, the system defaults
        safely to 0mm / clear weather behavior without crashing, and does not 
        throw exceptions.
        """
        # Delete the weather snapshot entirely
        self.weather.delete()
        
        payload = {
            "origin_node": str(self.node_a),
            "destination_node": str(self.node_c)
        }
        
        response = self.client.post('/api/v1/routes/calculate/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        
        routes = data['routes']
        recommended = next(r for r in routes if r['recommended'])
        
        # ETA should still be calculable
        self.assertIsNotNone(recommended['adjusted_eta_minutes'])
        self.assertEqual(recommended['delay_severity'], 'none')
        # Ensure 'top_factors' doesn't complain about missing weather
        factors_str = " ".join(recommended.get('top_factors', []))
        self.assertNotIn("unavailable", factors_str)
