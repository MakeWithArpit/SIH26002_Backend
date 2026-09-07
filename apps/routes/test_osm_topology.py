from unittest.mock import patch
import networkx as nx
from django.test import TestCase
from django.core.management import call_command

from apps.routes.models import Infrastructure, District
from apps.routes.services.routing.graph import RoadNetworkGraphService


class OSMTopologyTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Mock OSMnx download to return a small controlled graph
        # instead of hitting the live OSM API during tests.
        
        cls.G = nx.MultiDiGraph()
        # Node 1: 101, Node 2: 102, Node 3: 103, Node 4: 104
        cls.G.add_node(101, x=91.0, y=26.0)
        cls.G.add_node(102, x=91.1, y=26.1)
        cls.G.add_node(103, x=91.2, y=26.2)
        cls.G.add_node(104, x=91.3, y=26.3)
        
        # 101 <-> 102 (Two-way)
        cls.G.add_edge(101, 102, osmid=500, oneway=False, length=1000.0, highway='primary')
        cls.G.add_edge(102, 101, osmid=500, oneway=False, length=1000.0, highway='primary')
        
        # 102 -> 103 (One-way)
        cls.G.add_edge(102, 103, osmid=501, oneway=True, length=2000.0, highway='secondary')
        
        # 101 <-> 103 (Parallel two-way alternative)
        cls.G.add_edge(101, 103, osmid=502, oneway=False, length=3000.0, highway='tertiary')
        cls.G.add_edge(103, 101, osmid=502, oneway=False, length=3000.0, highway='tertiary')
        
        # We patch osmnx.graph_from_place to return our mock graph
        with patch('osmnx.graph_from_place', return_value=cls.G):
            call_command('import_osm_network', place='Test Place')

    def test_infrastructure_records_created(self):
        self.assertEqual(Infrastructure.objects.count(), 3)
        
        two_way = Infrastructure.objects.get(osm_way_id=500)
        self.assertFalse(two_way.oneway)
        self.assertIn(two_way.start_node, [101, 102])
        self.assertIn(two_way.end_node, [101, 102])
        
        one_way = Infrastructure.objects.get(osm_way_id=501)
        self.assertTrue(one_way.oneway)
        self.assertEqual(one_way.start_node, 102)
        self.assertEqual(one_way.end_node, 103)

    def test_geometry_valid_linestrings(self):
        for infra in Infrastructure.objects.all():
            self.assertEqual(infra.geom.geom_type, 'LineString')
            self.assertGreaterEqual(len(infra.geom.coords), 2)

    def test_nodes_use_osm_ids(self):
        graph = RoadNetworkGraphService.build_graph()
        for node in graph.nodes:
            self.assertIsInstance(node, int)
            self.assertGreater(node, 100)

    def test_one_way_directionality_preserved_in_graph(self):
        graph = RoadNetworkGraphService.build_graph()
        infra_oneway = Infrastructure.objects.get(osm_way_id=501)
        
        # Graph must contain 102 -> 103 but not 103 -> 102
        self.assertTrue(graph.has_edge(102, 103))
        # Edge key should be the infra ID
        self.assertTrue(graph.has_edge(102, 103, key=infra_oneway.id))
        
        self.assertFalse(graph.has_edge(103, 102))

    def test_parallel_roads_not_overwritten(self):
        graph = RoadNetworkGraphService.build_graph()
        
        # 101 <-> 102 is connected
        self.assertTrue(graph.has_edge(101, 102))
        
        # 101 <-> 103 is connected directly (via 502)
        self.assertTrue(graph.has_edge(101, 103))
        
        # 102 -> 103 is connected directly (via 501)
        self.assertTrue(graph.has_edge(102, 103))
        
        # Multiple paths between 101 and 103 should exist
        paths = list(nx.all_simple_paths(graph, 101, 103))
        self.assertEqual(len(paths), 2) # [101, 103] and [101, 102, 103]

    def test_every_segment_represented_as_edge(self):
        graph = RoadNetworkGraphService.build_graph()
        for infra in Infrastructure.objects.all():
            if infra.oneway:
                self.assertTrue(graph.has_edge(infra.start_node, infra.end_node, key=infra.id))
                self.assertFalse(graph.has_edge(infra.end_node, infra.start_node, key=infra.id))
            else:
                self.assertTrue(graph.has_edge(infra.start_node, infra.end_node, key=infra.id))
                self.assertTrue(graph.has_edge(infra.end_node, infra.start_node, key=infra.id))

    def test_repeated_import_idempotency(self):
        count_before = Infrastructure.objects.count()
        self.assertEqual(count_before, 3) # 1 two-way, 1 one-way, 1 parallel
        
        with patch('osmnx.graph_from_place', return_value=self.G):
            call_command('import_osm_network', place='Test Place')
            
        count_after = Infrastructure.objects.count()
        self.assertEqual(count_after, count_before) # Should not create duplicates
        
        # Two-way segment not becoming two Infrastructure records
        two_way_qs = Infrastructure.objects.filter(osm_way_id=500)
        self.assertEqual(two_way_qs.count(), 1)
        
        # Parallel roads remaining separate
        parallel_qs = Infrastructure.objects.filter(osm_way_id=502)
        self.assertEqual(parallel_qs.count(), 1)
        
        # Distinct segments of the same way remaining separate
        # (This is structurally guaranteed by the `min_node` and `max_node` inclusion in `osm_segment_id`)
