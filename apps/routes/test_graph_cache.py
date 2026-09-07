from unittest.mock import patch
from django.test import TestCase
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon
import networkx as nx

from apps.routes.models import District, Infrastructure, InfrastructureType, RoadClassification
from apps.routes.services.routing.graph import RoadNetworkGraphService


class GraphCacheTests(TestCase):
    def setUp(self):
        RoadNetworkGraphService.clear_graph_cache()
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name='Cache Test District',
            state='Assam',
            accessibility_score=9.0,
            geom=MultiPolygon(poly),
        )
        self.infra = Infrastructure.objects.create(
            district=self.district,
            name='Segment 1',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=201,
            end_node=202,
            oneway=False,
            length_km=10.0,
            base_speed_kmh=50.0,
            geom=LineString([(0, 0), (1, 1)]),
        )

    def tearDown(self):
        RoadNetworkGraphService.clear_graph_cache()

    # 1. First graph request builds and caches the graph.
    def test_first_graph_request_builds_and_caches(self):
        self.assertIsNone(RoadNetworkGraphService._cached_graph)
        graph = RoadNetworkGraphService.get_graph()
        self.assertIsInstance(graph, nx.MultiDiGraph)
        self.assertIsNotNone(RoadNetworkGraphService._cached_graph)
        self.assertIs(RoadNetworkGraphService._cached_graph, graph)

    # 2. Second graph request returns the same cached graph object.
    def test_second_graph_request_returns_same_cached_object(self):
        graph1 = RoadNetworkGraphService.get_graph()
        with patch.object(RoadNetworkGraphService, 'build_graph', wraps=RoadNetworkGraphService.build_graph) as mock_build:
            graph2 = RoadNetworkGraphService.get_graph()
            mock_build.assert_not_called()
        self.assertIs(graph1, graph2)

    # 3. clear_graph_cache() removes the cached graph.
    def test_clear_graph_cache_removes_cached_graph(self):
        RoadNetworkGraphService.get_graph()
        self.assertIsNotNone(RoadNetworkGraphService._cached_graph)
        RoadNetworkGraphService.clear_graph_cache()
        self.assertIsNone(RoadNetworkGraphService._cached_graph)

    # 4. After clearing the cache, the next request rebuilds the graph.
    def test_next_request_after_clear_rebuilds_graph(self):
        graph1 = RoadNetworkGraphService.get_graph()
        RoadNetworkGraphService.clear_graph_cache()
        self.assertIsNone(RoadNetworkGraphService._cached_graph)
        graph2 = RoadNetworkGraphService.get_graph()
        self.assertIsNotNone(graph2)
        self.assertIsNot(graph1, graph2)
        self.assertIs(RoadNetworkGraphService._cached_graph, graph2)

    # 5. reload_graph() replaces the cached graph.
    def test_reload_graph_replaces_cached_graph(self):
        graph1 = RoadNetworkGraphService.get_graph()
        reloaded_graph = RoadNetworkGraphService.reload_graph()
        self.assertIsNotNone(reloaded_graph)
        self.assertIsNot(graph1, reloaded_graph)
        self.assertIs(RoadNetworkGraphService._cached_graph, reloaded_graph)

    # 6. Routing flow uses the cached graph without rebuilding.
    def test_routing_flow_uses_cached_graph(self):
        # Warm up the cache
        cached_graph = RoadNetworkGraphService.get_graph()
        with patch.object(RoadNetworkGraphService, 'build_graph') as mock_build:
            candidates = RoadNetworkGraphService.generate_candidate_routes(201, 202)
            mock_build.assert_not_called()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].segments[0]['id'], self.infra.id)

