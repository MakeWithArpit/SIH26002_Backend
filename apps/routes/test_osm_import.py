import os
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.management import call_command
from django.contrib.gis.geos import LineString
from apps.routes.models import Infrastructure, District
from apps.routes.services.routing.graph import RoadNetworkGraphService
import networkx as nx

class OsmImportTests(TestCase):
    def setUp(self):
        # Create a mock OSMnx graph to simulate `ox.graph_from_place`
        self.mock_G = nx.MultiDiGraph()
        
        # Add some mock nodes (OSM IDs)
        self.mock_G.add_node(101, x=91.80, y=25.50)
        self.mock_G.add_node(102, x=91.81, y=25.51)
        self.mock_G.add_node(103, x=91.82, y=25.52)
        
        # Add a two-way edge (creates two directed edges in MultiDiGraph from OSMnx)
        self.mock_G.add_edge(101, 102, key=0, osmid=1001, oneway=False, length=1000.0, highway='primary', name='Main St')
        self.mock_G.add_edge(102, 101, key=0, osmid=1001, oneway=False, length=1000.0, highway='primary', name='Main St')
        
        # Add a parallel two-way edge (different osmid)
        self.mock_G.add_edge(101, 102, key=1, osmid=1002, oneway=False, length=1200.0, highway='secondary', name='Alt St')
        self.mock_G.add_edge(102, 101, key=1, osmid=1002, oneway=False, length=1200.0, highway='secondary', name='Alt St')
        
        # Add a one-way edge
        self.mock_G.add_edge(102, 103, key=0, osmid=1003, oneway=True, length=800.0, highway='tertiary', name='One Way St')

    @patch('osmnx.graph_from_place')
    def test_osm_import_command(self, mock_graph_from_place):
        mock_graph_from_place.return_value = self.mock_G
        
        # Run command
        call_command('import_osm_corridor')
        
        # Should have created 1 district
        self.assertEqual(District.objects.filter(name="Shillong OSM Area").count(), 1)
        
        # Should have created exactly 3 Infrastructure segments:
        # 1001 (two-way), 1002 (parallel two-way), 1003 (one-way)
        infras = Infrastructure.objects.all()
        self.assertEqual(infras.count(), 3)
        
        # Test parallel roads not overwritten
        edges_101_102 = Infrastructure.objects.filter(start_node=101, end_node=102) | Infrastructure.objects.filter(start_node=102, end_node=101)
        self.assertEqual(edges_101_102.count(), 2)
        
        # Test one-way is preserved
        oneway_edge = Infrastructure.objects.get(osm_way_id=1003)
        self.assertTrue(oneway_edge.oneway)
        self.assertEqual(oneway_edge.start_node, 102)
        self.assertEqual(oneway_edge.end_node, 103)
        
        # Verify line strings are valid
        for infra in infras:
            self.assertIsInstance(infra.geom, LineString)
            self.assertTrue(infra.geom.valid)
            self.assertIsInstance(infra.start_node, int)
            self.assertIsInstance(infra.end_node, int)
            
        # Verify graph integration (GraphService can build a graph from these records)
        graph = RoadNetworkGraphService.build_graph()
        self.assertIsInstance(graph, nx.MultiDiGraph)
        
        # Two-way road yields both directions in graph
        self.assertTrue(graph.has_edge(101, 102))
        self.assertTrue(graph.has_edge(102, 101))
        
        # One-way road yields only permitted direction
        self.assertTrue(graph.has_edge(102, 103))
        self.assertFalse(graph.has_edge(103, 102))
        
        # Both parallel roads are in the built graph
        self.assertEqual(len(graph[101][102]), 2)
        
        # The network has connected components (101 -> 103 is reachable)
        self.assertTrue(nx.has_path(graph, 101, 103))
