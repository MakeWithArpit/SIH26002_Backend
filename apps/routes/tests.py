import io
from PIL import Image
from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.gis.geos import MultiPolygon, Polygon, LineString
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Role
from apps.routes.models import (
    District,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
    HazardLevel,
    OperationalStatus,
)
from apps.routes.services.risk import RiskPredictionService
from apps.reports.models import IncidentReport, IncidentType, SeverityLevel


def get_test_image():
    file_obj = io.BytesIO()
    image = Image.new('RGB', (10, 10), color='blue')
    image.save(file_obj, format='JPEG')
    file_obj.seek(0)
    return SimpleUploadedFile('snap_test.jpg', file_obj.read(), content_type='image/jpeg')


class Phase2RoadNetworkAndRiskTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.admin = User.objects.create_user(username='admin_p2', password='Password123!')
        self.admin.profile.role = Role.ADMIN
        self.admin.profile.save()

        self.officer = User.objects.create_user(username='officer_p2', password='Password123!')
        self.officer.profile.role = Role.FIELD_OFFICER
        self.officer.profile.save()

        self.normal_user = User.objects.create_user(username='user_p2', password='Password123!')
        self.normal_user.profile.role = Role.NORMAL_USER
        self.normal_user.profile.save()

        # District
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name='Kamrup Test',
            state='Assam',
            accessibility_score=9.0,
            geom=MultiPolygon(poly),
        )

        # Road Segment 1 (Guwahati sector)
        self.seg1 = Infrastructure.objects.create(
            district=self.district,
            name='NH-06 Test Segment 1',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node='N1',
            end_node='N2',
            length_km=10.0,
            base_speed_kmh=50.0,
            landslide_susceptibility=HazardLevel.LOW,
            flood_hazard_zone=HazardLevel.LOW,
            historical_landslide_count=0,
            recent_rainfall_mm=0.0,
            weather_warning=False,
            geom=LineString([(91.75, 26.18), (91.80, 26.15), (91.85, 26.10)]),
        )
        RiskPredictionService.assess_and_update(self.seg1)

        # Road Segment 2 (High Risk Mountain Pass)
        self.seg2 = Infrastructure.objects.create(
            district=self.district,
            name='NH-06 Steep Mountain Pass',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node='N2',
            end_node='N3',
            length_km=25.0,
            base_speed_kmh=40.0,
            landslide_susceptibility=HazardLevel.HIGH,
            flood_hazard_zone=HazardLevel.MEDIUM,
            historical_landslide_count=5,
            recent_rainfall_mm=60.0,
            weather_warning=True,
            geom=LineString([(91.85, 26.10), (91.88, 26.00)]),
        )
        RiskPredictionService.assess_and_update(self.seg2)

        # Road Segment 3 (Safe Detour Bypass connecting N1 to N3 directly)
        self.seg3 = Infrastructure.objects.create(
            district=self.district,
            name='Test Safe Detour Bypass',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.STATE_HIGHWAY,
            start_node='N1',
            end_node='N3',
            length_km=38.0,
            base_speed_kmh=50.0,
            landslide_susceptibility=HazardLevel.LOW,
            flood_hazard_zone=HazardLevel.LOW,
            historical_landslide_count=0,
            recent_rainfall_mm=0.0,
            weather_warning=False,
            geom=LineString([(91.75, 26.18), (91.82, 26.08), (91.88, 26.00)]),
        )
        RiskPredictionService.assess_and_update(self.seg3)

    def test_districts_list_and_retrieve(self):
        self.client.force_authenticate(user=self.normal_user)
        res = self.client.get('/api/v1/routes/districts/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertGreaterEqual(len(data['data']), 1)
        self.assertEqual(data['data'][0]['name'], 'Kamrup Test')
        self.assertIn('geojson', data['data'][0])

    def test_infrastructure_list_and_filters(self):
        self.client.force_authenticate(user=self.normal_user)
        # Filter by risk_level=high
        res = self.client.get('/api/v1/routes/infrastructure/?risk_level=high')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.json()['data']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['name'], 'NH-06 Steep Mountain Pass')

    def test_infrastructure_proximity_query(self):
        self.client.force_authenticate(user=self.normal_user)
        # Query near coordinate (26.18, 91.75) within 2000m
        url = '/api/v1/routes/infrastructure/?lat=26.18&lng=91.75&radius_m=2000'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.json()['data']
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]['id'], self.seg1.id)

    def test_rule_based_risk_engine_contract(self):
        # seg2 has: high landslide (+30) + historical (+15) + medium flood (+15) + rain>50 (+25) + warning (+10) = 95
        assessment = RiskPredictionService.calculate_risk(self.seg2)
        self.assertEqual(assessment['risk_level'], 'high')
        self.assertEqual(assessment['risk_score'], 95.0)
        self.assertEqual(assessment['disruption_probability'], 0.95)
        self.assertIn('high landslide susceptibility', assessment['top_factors'])
        self.assertIn('heavy rainfall (60.0mm)', assessment['top_factors'])
        self.assertIn('active IMD weather warning', assessment['top_factors'])

    def test_assess_risk_endpoint_action(self):
        self.client.force_authenticate(user=self.admin)
        # Apply simulated heavy rain on seg1 (currently risk 0)
        payload = {
            'recent_rainfall_mm': 65.0,
            'weather_warning': True,
        }
        url = f'/api/v1/routes/infrastructure/{self.seg1.id}/assess-risk/'
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()['data']

        # seg1 rain > 50 (+25) + warning (+10) = 35.0 (low/medium threshold)
        self.assertGreaterEqual(data['risk_score'], 35.0)
        self.seg1.refresh_from_db()
        self.assertEqual(self.seg1.recent_rainfall_mm, 65.0)

    def test_spatial_snapping_of_incident_report_updates_infrastructure_risk(self):
        # seg1 initially has low risk
        self.client.force_authenticate(user=self.officer)
        initial_score = self.seg1.risk_score

        # Officer submits flood report near seg1 (26.175, 91.760)
        payload = {
            'photo': get_test_image(),
            'latitude': 26.1750,
            'longitude': 91.7600,
            'description': 'Waterlogging across road segment.',
            'incident_type': IncidentType.FLOOD,
            'severity': SeverityLevel.HIGH,
            'client_timestamp': timezone.now().isoformat(),
        }
        res = self.client.post('/api/v1/reports/incidents/', payload, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        rep_data = res.json()['data']

        # Verify report snapped to seg1
        self.assertEqual(rep_data['snapped_infrastructure'], self.seg1.id)
        self.assertEqual(rep_data['snapped_infrastructure_name'], self.seg1.name)

        # Verify seg1 risk was updated (+20 for recent incident report)
        self.seg1.refresh_from_db()
        self.assertGreater(self.seg1.risk_score, initial_score)
        self.assertIn('recent field incident report', self.seg1.top_factors)

    def test_normal_user_cannot_create_or_delete_infrastructure(self):
        self.client.force_authenticate(user=self.normal_user)
        # Attempt to create
        res = self.client.post('/api/v1/routes/infrastructure/', {'name': 'Hacked Road'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # ── Phase 3: Route Calculation & Risk Optimization Tests ─────────────

    def test_route_calculation_recommends_safe_detour_when_shortest_is_hazardous(self):
        """
        N1 -> N2 -> N3: distance 35 km, but seg2 has risk 95.0.
        N1 -> N3 (Bypass): distance 38 km (3 km longer), but risk is 0.0.
        Engine must generate both candidates and recommend the safe bypass.
        """
        self.client.force_authenticate(user=self.normal_user)
        payload = {
            'origin_node': 'N1',
            'destination_node': 'N3',
        }
        res = self.client.post('/api/v1/routes/calculate/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()['data']

        self.assertEqual(data['origin_node'], 'N1')
        self.assertEqual(data['destination_node'], 'N3')
        routes = data['routes']
        self.assertGreaterEqual(len(routes), 2)

        # Recommended route is sorted first
        recommended_route = routes[0]
        self.assertTrue(recommended_route['recommended'])
        self.assertEqual(recommended_route['route_id'], 'route-safe')
        self.assertEqual(recommended_route['distance_km'], 38.0)
        self.assertEqual(recommended_route['risk_level'], 'low')
        self.assertIn('Recommended for safety', recommended_route['explanation'])

        # Shortest route is second and not recommended
        shortest_route = next(r for r in routes if r['route_id'] == 'route-shortest')
        self.assertFalse(shortest_route['recommended'])
        self.assertEqual(shortest_route['distance_km'], 35.0)
        self.assertEqual(shortest_route['risk_level'], 'high')
        self.assertIn('NOT recommended', shortest_route['explanation'])

    def test_route_calculation_recommends_shortest_when_risk_is_acceptable(self):
        """
        If mountain pass seg2 risk drops to 0, shortest route should be recommended.
        """
        self.seg2.landslide_susceptibility = HazardLevel.LOW
        self.seg2.recent_rainfall_mm = 0.0
        self.seg2.weather_warning = False
        self.seg2.historical_landslide_count = 0
        self.seg2.flood_hazard_zone = HazardLevel.LOW
        RiskPredictionService.assess_and_update(self.seg2)

        self.client.force_authenticate(user=self.normal_user)
        payload = {'origin_node': 'N1', 'destination_node': 'N3'}
        res = self.client.post('/api/v1/routes/calculate/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        routes = res.json()['data']['routes']

        recommended = routes[0]
        self.assertTrue(recommended['recommended'])
        self.assertEqual(recommended['route_id'], 'route-shortest')
        self.assertEqual(recommended['distance_km'], 35.0)
        self.assertEqual(recommended['risk_level'], 'low')

    def test_route_calculation_by_coordinates(self):
        """Test resolving lat/lng coordinates to nearest nodes and calculating route."""
        self.client.force_authenticate(user=self.normal_user)
        # Coords near N1 (26.18, 91.75) and N3 (26.00, 91.88)
        payload = {
            'origin_lat': 26.18,
            'origin_lng': 91.75,
            'destination_lat': 26.00,
            'destination_lng': 91.88,
        }
        res = self.client.post('/api/v1/routes/calculate/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()['data']
        self.assertEqual(data['origin_node'], 'N1')
        self.assertEqual(data['destination_node'], 'N3')
        self.assertGreaterEqual(len(data['routes']), 1)
        self.assertIn('polyline', data['routes'][0])

    def test_route_calculation_unauthenticated_rejected(self):
        res = self.client.post('/api/v1/routes/calculate/', {'origin_node': 'N1', 'destination_node': 'N3'})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

