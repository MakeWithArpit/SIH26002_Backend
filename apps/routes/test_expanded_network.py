import os
import django
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import networkx as nx

from apps.routes.models import Infrastructure, District
from apps.routes.services.routing.graph import RoadNetworkGraphService, _haversine_km
from apps.routes.services.route_ranking import RouteRankingService
from apps.intelligence.services.eta.engine import ETAEngine

User = get_user_model()


class ExpandedRoadNetworkGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command('import_ner_network')

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='test_officer',
            password='Password123!'
        )
        self.client.force_authenticate(user=self.user)

    def test_graph_coverage_and_connectivity(self):
        graph = RoadNetworkGraphService.get_graph(force_reload=True)
        self.assertGreater(len(graph.nodes), 1000, "Graph must contain over 1,000 genuine OSM nodes")
        self.assertGreater(len(graph.edges), 2000, "Graph must contain over 2,000 genuine OSM edges")

        # 1. Verify city snapping locations
        cities = {
            'Guwahati': (26.1822, 91.7509),
            'Shillong': (25.5788, 91.8845),
            'Dimapur': (25.9068, 93.7271),
        }

        snapped = {}
        for name, (lat, lng) in cities.items():
            node = RoadNetworkGraphService.find_nearest_node(lat, lng, max_distance_km=35.0)
            self.assertIsNotNone(node, f"{name} failed to snap to graph node")
            node_x = graph.nodes[node]['x']
            node_y = graph.nodes[node]['y']
            snap_dist = _haversine_km(lat, lng, node_y, node_x)
            self.assertLess(snap_dist, 1.0, f"{name} snapping distance {snap_dist:.2f}km exceeds 1.0km threshold")
            snapped[name] = node

        # 2. Verify Graph-level 6-directional connectivity
        pairs = [
            ('Guwahati', 'Shillong', 80.0, 120.0),
            ('Shillong', 'Guwahati', 80.0, 120.0),
            ('Guwahati', 'Dimapur', 230.0, 300.0),
            ('Dimapur', 'Guwahati', 230.0, 300.0),
            ('Shillong', 'Dimapur', 270.0, 360.0),
            ('Dimapur', 'Shillong', 270.0, 360.0),
        ]

        for src, dst, min_km, max_km in pairs:
            u = snapped[src]
            v = snapped[dst]
            self.assertTrue(nx.has_path(graph, u, v), f"No graph path from {src} to {dst}")
            dist = nx.shortest_path_length(graph, u, v, weight='weight_distance')
            self.assertGreaterEqual(dist, min_km, f"{src}->{dst} distance {dist:.1f}km too small (min {min_km})")
            self.assertLessEqual(dist, max_km, f"{src}->{dst} distance {dist:.1f}km too large (max {max_km})")

    def test_api_route_calculation_all_city_pairs(self):
        city_coords = {
            'Guwahati': (26.1822, 91.7509),
            'Shillong': (25.5788, 91.8845),
            'Dimapur': (25.9068, 93.7271),
        }

        pairs = [
            ('Guwahati', 'Shillong'),
            ('Shillong', 'Guwahati'),
            ('Guwahati', 'Dimapur'),
            ('Dimapur', 'Guwahati'),
            ('Shillong', 'Dimapur'),
            ('Dimapur', 'Shillong'),
        ]

        for src_name, dst_name in pairs:
            src_lat, src_lng = city_coords[src_name]
            dst_lat, dst_lng = city_coords[dst_name]

            res = self.client.post('/api/v1/routes/calculate/', {
                'origin_lat': src_lat,
                'origin_lng': src_lng,
                'destination_lat': dst_lat,
                'destination_lng': dst_lng,
            }, format='json')

            self.assertEqual(res.status_code, status.HTTP_200_OK, f"API failed for {src_name} -> {dst_name}: {res.data}")
            self.assertTrue(res.data.get('success'), f"Success not True for {src_name} -> {dst_name}")

            routes = res.data['data']['routes']
            self.assertGreaterEqual(len(routes), 1, f"Zero candidate routes for {src_name} -> {dst_name}")

            rec = next((r for r in routes if r.get('recommended')), routes[0])
            self.assertIn('distance_km', rec)
            self.assertIn('adjusted_eta_minutes', rec)
            self.assertIn('polyline', rec)
            self.assertGreater(len(rec['polyline']), 10, f"Polyline has too few waypoints for {src_name} -> {dst_name}")

            # Verify polyline start is near origin and end is near destination
            start_coord = rec['polyline'][0] # [lat, lng]
            end_coord = rec['polyline'][-1] # [lat, lng]

            start_dist = _haversine_km(src_lat, src_lng, start_coord[0], start_coord[1])
            end_dist = _haversine_km(dst_lat, dst_lng, end_coord[0], end_coord[1])

            self.assertLess(start_dist, 5.0, f"Route start ({start_coord}) is {start_dist:.1f}km away from {src_name}")
            self.assertLess(end_dist, 5.0, f"Route end ({end_coord}) is {end_dist:.1f}km away from {dst_name}")

    def test_negative_unsupported_destination_rejected(self):
        # Aizawl, Mizoram: lat 23.7271, lng 92.7176 (~200km south of network)
        res = self.client.post('/api/v1/routes/calculate/', {
            'origin_lat': 26.1822,
            'origin_lng': 91.7509,
            'destination_lat': 23.7271,
            'destination_lng': 92.7176,
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get('success'))
        self.assertIn('outside the supported road network coverage', res.data.get('message', ''))

    def test_negative_unsupported_origin_rejected(self):
        # Imphal, Manipur: lat 24.8170, lng 93.9368 (~120km away from network)
        res = self.client.post('/api/v1/routes/calculate/', {
            'origin_lat': 24.8170,
            'origin_lng': 93.9368,
            'destination_lat': 26.1822,
            'destination_lng': 91.7509,
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get('success'))
        self.assertIn('outside the supported road network coverage', res.data.get('message', ''))
