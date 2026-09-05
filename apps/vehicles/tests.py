from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Role
from apps.vehicles.models import Vehicle, VehicleType, LocationPing, Trip, TripStatus
from apps.vehicles.services.eta import ETAEstimationService


class Phase4VehiclesAndETATests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Admin user
        self.admin = User.objects.create_user(username='admin_v4', password='Password123!')
        self.admin.profile.role = Role.ADMIN
        self.admin.profile.save()

        # Driver user
        self.driver = User.objects.create_user(username='driver_v4', password='Password123!')
        self.driver.profile.role = Role.NORMAL_USER
        self.driver.profile.save()

        # Normal viewer user
        self.viewer = User.objects.create_user(username='viewer_v4', password='Password123!')
        self.viewer.profile.role = Role.NORMAL_USER
        self.viewer.profile.save()

        # Fleet Vehicle
        self.vehicle = Vehicle.objects.create(
            registration_number='AS01AB1234',
            vehicle_type=VehicleType.TRUCK,
            driver=self.driver,
            capacity_tons=10.0,
        )

        # Active Trip (Guwahati to Shillong)
        self.trip = Trip.objects.create(
            trip_code='TRIP-GS-001',
            vehicle=self.vehicle,
            driver=self.driver,
            origin=Point(91.7500, 26.1833, srid=4326),
            origin_name='Guwahati City Hub',
            destination=Point(91.8933, 25.5788, srid=4326),
            destination_name='Shillong Police Bazar Depot',
            status=TripStatus.CREATED,
        )

    def test_vehicle_list_and_driver_details(self):
        self.client.force_authenticate(user=self.viewer)
        res = self.client.get('/api/v1/vehicles/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['data'][0]['registration_number'], 'AS01AB1234')
        self.assertEqual(data['data'][0]['driver_username'], 'driver_v4')

    def test_normal_user_cannot_create_vehicle(self):
        self.client.force_authenticate(user=self.viewer)
        payload = {
            'registration_number': 'AS01XX9999',
            'vehicle_type': VehicleType.VAN,
        }
        res = self.client.post('/api/v1/vehicles/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_location_ping_ingestion_and_atomic_telemetry_cache(self):
        """
        Ingesting a ping must create LocationPing and atomically update
        the Vehicle model's cached fields for O(1) polling.
        """
        self.client.force_authenticate(user=self.driver)
        now_ts = timezone.now()
        payload = {
            'lat': 26.1445,
            'lng': 91.7362,
            'speed': 38.5,
            'timestamp': now_ts.isoformat(),
        }
        url = f'/api/v1/vehicles/{self.vehicle.id}/locations/'
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.json()['success'])

        # 1. Verify historical LocationPing created
        self.assertEqual(LocationPing.objects.filter(vehicle=self.vehicle).count(), 1)
        ping = LocationPing.objects.first()
        self.assertAlmostEqual(ping.location.y, 26.1445, places=4)
        self.assertAlmostEqual(ping.location.x, 91.7362, places=4)
        self.assertEqual(ping.speed, 38.5)

        # 2. Verify Vehicle cached telemetry updated atomically
        self.vehicle.refresh_from_db()
        self.assertAlmostEqual(self.vehicle.current_lat, 26.1445, places=4)
        self.assertAlmostEqual(self.vehicle.current_lng, 91.7362, places=4)
        self.assertEqual(self.vehicle.current_speed, 38.5)
        self.assertIsNotNone(self.vehicle.last_ping_time)

        # 3. Verify O(1) latest location endpoint reads cached fields
        latest_url = f'/api/v1/vehicles/{self.vehicle.id}/location/latest/'
        latest_res = self.client.get(latest_url)
        self.assertEqual(latest_res.status_code, status.HTTP_200_OK)
        latest_data = latest_res.json()['data']
        self.assertAlmostEqual(latest_data['lat'], 26.1445, places=4)
        self.assertAlmostEqual(latest_data['lng'], 91.7362, places=4)
        self.assertEqual(latest_data['speed'], 38.5)

    def test_trip_creation_and_initial_eta(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            'trip_code': 'TRIP-TEST-002',
            'vehicle': self.vehicle.id,
            'origin_name': 'Jorabat Junction',
            'origin_lat': 26.1030,
            'origin_lng': 91.8650,
            'destination_name': 'Nongpoh Hub',
            'destination_lat': 25.9015,
            'destination_lng': 91.8780,
        }
        res = self.client.post('/api/v1/trips/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()['data']

        self.assertEqual(data['trip_code'], 'TRIP-TEST-002')
        self.assertEqual(data['status'], TripStatus.CREATED)
        self.assertGreater(data['base_eta_minutes'], 0.0)
        self.assertGreater(data['predicted_eta_minutes'], 0.0)
        self.assertIsNotNone(data['origin_coords'])
        self.assertIsNotNone(data['destination_coords'])

    def test_trip_status_lifecycle_start_and_complete(self):
        self.client.force_authenticate(user=self.driver)

        # 1. Start trip -> on_route
        start_url = f'/api/v1/trips/{self.trip.id}/start/'
        res_start = self.client.post(start_url)
        self.assertEqual(res_start.status_code, status.HTTP_200_OK)
        self.assertEqual(res_start.json()['data']['status'], TripStatus.ON_ROUTE)

        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, TripStatus.ON_ROUTE)
        self.assertIsNotNone(self.trip.start_time)

        # 2. Complete trip -> delivered
        complete_url = f'/api/v1/trips/{self.trip.id}/complete/'
        res_comp = self.client.post(complete_url)
        self.assertEqual(res_comp.status_code, status.HTTP_200_OK)
        self.assertEqual(res_comp.json()['data']['status'], TripStatus.DELIVERED)

        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, TripStatus.DELIVERED)
        self.assertIsNotNone(self.trip.end_time)

    def test_eta_estimation_service_penalties(self):
        """
        Unit test verifying condition-aware penalties:
        high risk road (+40-75% delay) and heavy rain (+25% delay).
        """
        segments = [
            {
                'name': 'NH-06 Plain Sector',
                'length_km': 20.0,
                'road_classification': 'national_highway',  # 50 km/h -> 24 mins base
                'risk_score': 10.0,
                'status': 'accessible',
            },
            {
                'name': 'NH-06 Mountain Pass',
                'length_km': 30.0,
                'road_classification': 'national_highway',  # 50 km/h -> 36 mins base
                'risk_score': 85.0,  # High risk -> severe delay
                'status': 'risky',
            },
        ]

        # Base time = 24 + 36 = 60 mins
        # Pass rainfall = 60mm (>50mm) -> +25% weather delay
        result = ETAEstimationService.calculate_eta_for_route(
            segments=segments,
            rainfall_mm=60.0,
        )

        self.assertEqual(result['base_eta_minutes'], 60.0)
        self.assertGreater(result['predicted_eta_minutes'], 60.0)
        self.assertGreaterEqual(result['expected_delay_minutes'], 30.0)
        self.assertIn(result['delay_severity'], ['moderate', 'critical'])

        # Explanatory factors
        factors_text = " ".join(result['top_factors'])
        self.assertIn('Hazardous segment', factors_text)
        self.assertIn('Heavy rainfall delay', factors_text)

    def test_recalculate_eta_action(self):
        self.client.force_authenticate(user=self.driver)
        url = f'/api/v1/trips/{self.trip.id}/recalculate-eta/'
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()['data']
        self.assertGreater(data['base_eta_minutes'], 0.0)
