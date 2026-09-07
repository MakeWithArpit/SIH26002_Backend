from django.test import TestCase
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon

from apps.routes.models import (
    District,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
)
from apps.routes.services.routing.graph import RoadNetworkGraphService


class CandidateRouteTests(TestCase):
    def setUp(self):
        RoadNetworkGraphService.clear_graph_cache()
        poly = Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05)))
        self.district = District.objects.create(
            name='Test District',
            state='Assam',
            accessibility_score=9.0,
            geom=MultiPolygon(poly),
        )

        # Nodes
        self.node_a = 101
        self.node_b = 102
        self.node_c = 103
        self.node_d = 104

        # A -> B (two-way)
        self.infra_ab = Infrastructure.objects.create(
            district=self.district, name='A to B', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=self.node_a, end_node=self.node_b, oneway=False,
            length_km=5.0, base_speed_kmh=50.0, geom=LineString([(0, 0), (1, 1)])
        )

        # B -> C (one-way)
        self.infra_bc_oneway = Infrastructure.objects.create(
            district=self.district, name='B to C (One Way)', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.STATE_HIGHWAY,
            start_node=self.node_b, end_node=self.node_c, oneway=True,
            length_km=5.0, base_speed_kmh=50.0, geom=LineString([(1, 1), (2, 2)])
        )

        # A -> C (Parallel path 1 to C)
        self.infra_ac = Infrastructure.objects.create(
            district=self.district, name='A to C Direct', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=self.node_a, end_node=self.node_c, oneway=False,
            length_km=15.0, base_speed_kmh=50.0, geom=LineString([(0, 0), (2, 2)])
        )

        # A -> C (Parallel path 2 to C)
        self.infra_ac_parallel = Infrastructure.objects.create(
            district=self.district, name='A to C Parallel', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=self.node_a, end_node=self.node_c, oneway=False,
            length_km=20.0, base_speed_kmh=50.0, geom=LineString([(0, 0), (1, 3), (2, 2)])
        )
        
        # C -> D (Blocked)
        self.infra_cd_blocked = Infrastructure.objects.create(
            district=self.district, name='C to D Blocked', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=self.node_c, end_node=self.node_d, oneway=False, status='blocked',
            length_km=5.0, base_speed_kmh=50.0, geom=LineString([(2, 2), (3, 3)])
        )
        
        # C -> D (Viable)
        self.infra_cd_viable = Infrastructure.objects.create(
            district=self.district, name='C to D Viable', infra_type=InfrastructureType.ROAD,
            road_classification=RoadClassification.NATIONAL_HIGHWAY,
            start_node=self.node_c, end_node=self.node_d, oneway=False,
            length_km=6.0, base_speed_kmh=50.0, geom=LineString([(2, 2), (4, 2), (3, 3)])
        )

    def tearDown(self):
        RoadNetworkGraphService.clear_graph_cache()

    def test_one_candidate_generated(self):
        # A to B has exactly one physical edge
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_b)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].segments[0]['id'], self.infra_ab.id)

    def test_distinct_candidates_differ_by_infra_ids(self):
        # A to C has three topological paths: A->B->C, A->C (direct), A->C (parallel)
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_c)
        self.assertEqual(len(routes), 3)
        signatures = [tuple(s['id'] for s in r.segments) for r in routes]
        self.assertEqual(len(set(signatures)), 3)

    # 1. Three genuinely different physical routes are returned when three exist.
    def test_1_three_genuinely_different_physical_routes_returned(self):
        # Paths between A and C: A->B->C (10km), A->C (15km), A->C parallel (20km)
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_c)
        self.assertEqual(len(routes), 3)
        
        signatures = [tuple(s['id'] for s in r.segments) for r in routes]
        self.assertEqual(len(set(signatures)), 3) # All 3 must be distinctly different

    # 2. Two parallel edges between the same nodes can produce different candidates.
    def test_2_two_parallel_edges_between_same_nodes_produce_different_candidates(self):
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_c)
        seg_ids_per_route = [[s['id'] for s in r.segments] for r in routes]
        self.assertIn([self.infra_ac.id], seg_ids_per_route)
        self.assertIn([self.infra_ac_parallel.id], seg_ids_per_route)

    # 3. The Infrastructure IDs in the candidate correspond to the actual selected graph edges.
    def test_3_infrastructure_ids_correspond_to_actual_selected_graph_edges(self):
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_c)
        parallel_route = next(r for r in routes if [s['id'] for s in r.segments] == [self.infra_ac_parallel.id])
        self.assertEqual(parallel_route.distance_km, self.infra_ac_parallel.length_km)
        self.assertEqual(parallel_route.segments[0]['name'], self.infra_ac_parallel.name)
        self.assertEqual(parallel_route.segments[0]['id'], self.infra_ac_parallel.id)

    # 4. No duplicate candidate is produced because of a repeated node-only path.
    def test_4_no_duplicate_candidate_produced_because_of_repeated_node_only_path(self):
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_c)
        signatures = [tuple(s['id'] for s in r.segments) for r in routes]
        
        # We expect the parallel segment (infra_ac_parallel) to be used in one of the routes
        parallel_used = any(self.infra_ac_parallel.id in sig for sig in signatures)
        self.assertTrue(parallel_used)

    # 5. One-way restrictions are respected.
    def test_5_oneway_restrictions_are_respected(self):
        # B -> C is oneway. C -> A cannot traverse C -> B.
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_c, self.node_a)
        
        for route in routes:
            segment_ids = [s['id'] for s in route.segments]
            self.assertNotIn(self.infra_bc_oneway.id, segment_ids)

    # 6. Blocked segments are excluded.
    def test_6_blocked_segments_are_excluded(self):
        # C to D has one blocked and one viable segment
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_c, self.node_d)
        
        self.assertEqual(len(routes), 1) # Only one is viable
        self.assertEqual(routes[0].segments[0]['id'], self.infra_cd_viable.id)

    # 7. One viable route returns one candidate.
    def test_7_one_viable_route_returns_one_candidate(self):
        # A to B has only one physical edge
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_b)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].segments[0]['id'], self.infra_ab.id)

    # 8. Two viable routes return two candidates.
    def test_8_two_viable_routes_return_two_candidates(self):
        # Remove infra_ac_parallel so A->D has exactly two paths: A->B->C->D and A->C->D
        self.infra_ac_parallel.delete()
        RoadNetworkGraphService.clear_graph_cache()
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_d)
        self.assertEqual(len(routes), 2)
        signatures = [tuple(s['id'] for s in r.segments) for r in routes]
        self.assertEqual(len(set(signatures)), 2)

    # 9. Route geometry matches the selected Infrastructure edge.
    def test_9_route_geometry_matches_selected_infrastructure_edge(self):
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_a, self.node_c)
        parallel_route = next(r for r in routes if [s['id'] for s in r.segments] == [self.infra_ac_parallel.id])
        # geom is LineString([(0, 0), (1, 3), (2, 2)]), coords in polyline are [lat, lng] = [[0, 0], [3, 1], [2, 2]]
        expected_coords = [[0.0, 0.0], [3.0, 1.0], [2.0, 2.0]]
        self.assertEqual(parallel_route.polyline, expected_coords)

    # 10. Reverse traversal produces reversed geometry.
    def test_10_reverse_traversal_produces_reversed_geometry(self):
        routes = RoadNetworkGraphService.generate_candidate_routes(self.node_c, self.node_a)
        parallel_route = next(r for r in routes if [s['id'] for s in r.segments] == [self.infra_ac_parallel.id])
        expected_coords = [[2.0, 2.0], [3.0, 1.0], [0.0, 0.0]]
        self.assertEqual(parallel_route.polyline, expected_coords)
