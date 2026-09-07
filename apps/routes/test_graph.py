import networkx as nx
from django.test import TestCase
from django.contrib.gis.geos import MultiPolygon, Polygon, LineString

from apps.routes.models import (
    District,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
    HazardLevel,
)
from apps.routes.services.routing.graph import RoadNetworkGraphService


class GraphFoundationTests(TestCase):
    def setUp(self):
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name='Test District',
            state='Assam',
            accessibility_score=9.0,
            geom=MultiPolygon(poly),
        )

        # OSM-style IDs
        self.node_a = 1000000001
        self.node_b = 1000000002
        self.node_c = 1000000003

        # Two-way road (node_a <-> node_b)
        self.infra_twoway = Infrastructure.objects.create(
            district=self.district,
            name='Two-way segment',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=self.node_a,
            end_node=self.node_b,
            oneway=False,
            length_km=5.0,
            base_speed_kmh=50.0,
            geom=LineString([(91.75, 26.18), (91.80, 26.15)]),
        )

        # Parallel two-way road (node_a <-> node_b) - alternative route
        self.infra_parallel = Infrastructure.objects.create(
            district=self.district,
            name='Parallel segment',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.STATE_HIGHWAY,
            start_node=self.node_a,
            end_node=self.node_b,
            oneway=False,
            length_km=6.0,
            base_speed_kmh=40.0,
            geom=LineString([(91.75, 26.18), (91.78, 26.17), (91.80, 26.15)]),
        )

        # One-way road (node_b -> node_c)
        self.infra_oneway = Infrastructure.objects.create(
            district=self.district,
            name='One-way segment',
            infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.MAJOR_DISTRICT_ROAD,
            start_node=self.node_b,
            end_node=self.node_c,
            oneway=True,
            length_km=3.0,
            base_speed_kmh=30.0,
            geom=LineString([(91.80, 26.15), (91.85, 26.10)]),
        )

    def test_multidigraph_is_used(self):
        graph = RoadNetworkGraphService.build_graph()
        self.assertIsInstance(graph, nx.MultiDiGraph)

    def test_nodes_use_osm_style_ids(self):
        graph = RoadNetworkGraphService.build_graph()
        self.assertIn(self.node_a, graph.nodes)
        self.assertIn(self.node_b, graph.nodes)
        self.assertIn(self.node_c, graph.nodes)
        self.assertIsInstance(list(graph.nodes)[0], int)

    def test_two_way_infrastructure_produces_both_directions(self):
        graph = RoadNetworkGraphService.build_graph()
        # Should have directed edges a->b and b->a for the first infra
        self.assertTrue(graph.has_edge(self.node_a, self.node_b, key=self.infra_twoway.id))
        self.assertTrue(graph.has_edge(self.node_b, self.node_a, key=self.infra_twoway.id))

    def test_one_way_edges_represented_in_permitted_direction_only(self):
        graph = RoadNetworkGraphService.build_graph()
        # Should have directed edge b->c but NOT c->b
        self.assertTrue(graph.has_edge(self.node_b, self.node_c, key=self.infra_oneway.id))
        self.assertFalse(graph.has_edge(self.node_c, self.node_b))

    def test_parallel_edges_are_preserved(self):
        graph = RoadNetworkGraphService.build_graph()
        # Both twoway and parallel infra exist between a and b
        edges = graph[self.node_a][self.node_b]
        self.assertEqual(len(edges), 2)
        self.assertIn(self.infra_twoway.id, edges)
        self.assertIn(self.infra_parallel.id, edges)
        
        # Ensure alternative physical road is not overwritten
        self.assertEqual(edges[self.infra_twoway.id]['name'], 'Two-way segment')
        self.assertEqual(edges[self.infra_parallel.id]['name'], 'Parallel segment')

    def test_edge_retains_infrastructure_reference_and_attributes(self):
        graph = RoadNetworkGraphService.build_graph()
        edge = graph[self.node_a][self.node_b][self.infra_twoway.id]
        
        self.assertEqual(edge['infrastructure_id'], self.infra_twoway.id)
        self.assertEqual(edge['distance_km'], 5.0)
        self.assertEqual(edge['base_travel_time_min'], self.infra_twoway.base_travel_time_min)
        self.assertEqual(edge['road_type'], RoadClassification.NATIONAL_HIGHWAY)
        self.assertIsNotNone(edge['geometry'])
        self.assertIn('risk_score', edge)
        self.assertIn('status', edge)
        self.assertFalse(edge['oneway'])
    def tearDown(self):
        RoadNetworkGraphService.clear_graph_cache()

    def test_routing_selects_lower_weight_parallel_segment(self):
        RoadNetworkGraphService.clear_graph_cache()
        # Generate candidate routes between node_a and node_b
        # Shortest path (weight_distance) should prefer infra_twoway (length_km=5.0) over infra_parallel (length_km=6.0)
        candidates = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_b)
        
        shortest_route = candidates[0]
        self.assertEqual(len(shortest_route.segments), 1)
        self.assertEqual(shortest_route.segments[0]['id'], self.infra_twoway.id)
        self.assertEqual(shortest_route.segments[0]['name'], 'Two-way segment')

        # Modify risk to force safely-weighted path to choose the parallel road
        # Block the shorter road and clear cache to verify candidate generation falls back to parallel segment
        self.infra_twoway.status = 'blocked'
        self.infra_twoway.save()
        RoadNetworkGraphService.clear_graph_cache()
        
        candidates_after_block = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_b)
        
        self.assertEqual(len(candidates_after_block), 1)
        remaining_route = candidates_after_block[0]
        self.assertEqual(remaining_route.segments[0]['id'], self.infra_parallel.id)
        self.assertEqual(remaining_route.segments[0]['name'], 'Parallel segment')
