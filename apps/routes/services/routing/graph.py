"""
Road Network Graph Service — NetworkX pathfinding on PostGIS Infrastructure.

Builds graph from Infrastructure segments and calculates:
1. Shortest Path (pure distance/travel time)
2. Safest Path (risk-penalized edge weights)
Produces ephemeral RouteCandidate objects (never stored in DB).
"""
import heapq
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
import networkx as nx
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

from apps.routes.models import Infrastructure

logger = logging.getLogger(__name__)


@dataclass
class RouteCandidate:
    """
    Ephemeral route calculation response shape.
    Never persisted as a database model.
    """
    route_id: str
    name: str
    distance_km: float
    base_eta_minutes: float
    risk_score: float
    risk_level: str
    recommended: bool = False
    explanation: str = ''
    polyline: List[List[float]] = field(default_factory=list)
    segments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'route_id': self.route_id,
            'name': self.name,
            'distance_km': round(self.distance_km, 2),
            'base_eta_minutes': round(self.base_eta_minutes, 1),
            'risk_score': round(self.risk_score, 1),
            'risk_level': self.risk_level,
            'recommended': self.recommended,
            'explanation': self.explanation,
            'polyline': self.polyline,
            'segments': self.segments,
        }


class RoadNetworkGraphService:
    _cached_graph: Optional[nx.MultiDiGraph] = None

    @classmethod
    def get_graph(cls, force_reload: bool = False) -> nx.MultiDiGraph:
        """
        Retrieve the cached road network MultiDiGraph.
        If cache is empty or force_reload is True, builds and stores the graph.
        """
        if cls._cached_graph is None or force_reload:
            cls._cached_graph = cls.build_graph()
        return cls._cached_graph

    @classmethod
    def clear_graph_cache(cls) -> None:
        """
        Clear the in-memory graph cache completely.
        """
        cls._cached_graph = None

    @classmethod
    def reload_graph(cls) -> nx.MultiDiGraph:
        """
        Clear existing cache, rebuild from current Infrastructure data,
        cache and return the new graph.
        """
        cls.clear_graph_cache()
        return cls.get_graph()

    @classmethod
    def build_graph(cls) -> nx.MultiDiGraph:
        """
        Construct a NetworkX MultiDiGraph from all active Infrastructure segments.
        Blocked segments are strictly excluded from candidate routing.
        """
        graph = nx.MultiDiGraph()
        infrastructures = Infrastructure.objects.select_related('district').all()

        for infra in infrastructures:
            # BLOCKED ROADS: strictly exclude them from graph-level routing
            if infra.status == 'blocked':
                continue

            coords = []
            if infra.geom:
                coords = [[pt[1], pt[0]] for pt in infra.geom.coords]

            length = infra.length_km if infra.length_km > 0 else 0.001

            edge_data = {
                'infrastructure_id': infra.id,
                'distance_km': infra.length_km,
                'base_travel_time_min': infra.base_travel_time_min,
                'road_type': infra.road_classification,
                'geometry': infra.geom.wkt if infra.geom else None,
                'risk_score': infra.risk_score,
                'risk_level': infra.risk_level,
                'status': infra.status,
                'oneway': infra.oneway,
                
                # Metadata & routing fields
                'id': infra.id,
                'name': infra.name,
                'coords': coords,
                'weight_distance': length,
            }

            # Add nodes with their coordinates
            if coords:
                start_coord = coords[0]
                end_coord = coords[-1]
                graph.add_node(infra.start_node, x=start_coord[1], y=start_coord[0])
                graph.add_node(infra.end_node, x=end_coord[1], y=end_coord[0])

            graph.add_edge(infra.start_node, infra.end_node, key=infra.id, **edge_data)
            
            if not infra.oneway:
                rev_coords = list(reversed(coords))
                rev_edge_data = edge_data.copy()
                rev_edge_data['coords'] = rev_coords
                graph.add_edge(infra.end_node, infra.start_node, key=infra.id, **rev_edge_data)

        return graph

    @classmethod
    def find_nearest_node(cls, lat: float, lng: float) -> Optional[int]:
        """
        Find the closest road graph node to the given coordinates.
        """
        point = Point(lng, lat, srid=4326)
        nearest_infra = Infrastructure.objects.annotate(
            dist=Distance('geom', point)
        ).order_by('dist').first()

        if not nearest_infra or not nearest_infra.geom:
            return None

        coords = nearest_infra.geom.coords
        start_pt = Point(coords[0][0], coords[0][1], srid=4326)
        end_pt = Point(coords[-1][0], coords[-1][1], srid=4326)

        dist_to_start = point.distance(start_pt)
        dist_to_end = point.distance(end_pt)

        return nearest_infra.start_node if dist_to_start <= dist_to_end else nearest_infra.end_node

    @classmethod
    def _dijkstra_multigraph(
        cls,
        graph: nx.MultiDiGraph,
        source: Any,
        target: Any,
        weight: str = 'weight_distance',
        excluded_nodes: Optional[Set[Any]] = None,
        excluded_edges: Optional[Set[Tuple[Any, Any, Any]]] = None,
    ) -> Tuple[Optional[float], Optional[List[Tuple[Any, Any, Any]]]]:
        """
        Dijkstra shortest path on MultiDiGraph preserving exact (u, v, key) edges.
        Does not mutate the graph; respects excluded_nodes and excluded_edges.
        """
        if excluded_nodes is None:
            excluded_nodes = set()
        if excluded_edges is None:
            excluded_edges = set()

        if source in excluded_nodes or target in excluded_nodes:
            return None, None

        heap = [(0.0, 0, source)]
        counter = 0
        dist = {source: 0.0}
        parent = {source: None}  # node -> (predecessor_node, edge_key)

        while heap:
            d, _, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            if u == target:
                break

            for v in graph[u]:
                if v in excluded_nodes:
                    continue
                for key, data in graph[u][v].items():
                    if (u, v, key) in excluded_edges:
                        continue
                    w = data.get(weight, 1.0)
                    new_d = d + w
                    if v not in dist or new_d < dist[v]:
                        dist[v] = new_d
                        parent[v] = (u, key)
                        counter += 1
                        heapq.heappush(heap, (new_d, counter, v))

        if target not in dist:
            return None, None

        # Reconstruct exact (u, v, key) edge path
        curr = target
        path = []
        while parent[curr] is not None:
            p, k = parent[curr]
            path.append((p, curr, k))
            curr = p
        path.reverse()
        return dist[target], path

    @classmethod
    def find_k_shortest_paths(
        cls,
        graph: nx.MultiDiGraph,
        source: Any,
        target: Any,
        K: int = 3,
        weight: str = 'weight_distance',
    ) -> List[List[Tuple[Any, Any, Any]]]:
        """
        Yen's K-shortest simple paths algorithm adapted for MultiDiGraph.
        Returns up to K distinct paths, where each path is a list of (u, v, key) tuples.
        Distinctness is determined by the physical sequence of edge keys (Infrastructure IDs).
        """
        cost, first_path = cls._dijkstra_multigraph(graph, source, target, weight=weight)
        if first_path is None:
            return []

        A = [first_path]
        seen_A = {tuple(e[2] for e in first_path)}
        B = []  # min-heap of (cost, counter, path)
        seen_B = set()
        counter = 0

        for k in range(1, K):
            prev_path = A[k - 1]
            nodes = [prev_path[0][0]] + [e[1] for e in prev_path]

            for i in range(len(prev_path)):
                spur_node = nodes[i]
                root_path = prev_path[:i]
                root_cost = sum(
                    graph[e[0]][e[1]][e[2]].get(weight, 1.0) for e in root_path
                )

                # Edges that share the same root path prefix must be excluded
                excluded_edges = set()
                for p in A:
                    if len(p) > i and p[:i] == root_path:
                        excluded_edges.add(p[i])

                # Root nodes (except spur_node) must be excluded to prevent loops
                excluded_nodes = set(nodes[:i])

                spur_cost, spur_path = cls._dijkstra_multigraph(
                    graph,
                    spur_node,
                    target,
                    weight=weight,
                    excluded_nodes=excluded_nodes,
                    excluded_edges=excluded_edges,
                )

                if spur_path is not None:
                    total_path = root_path + spur_path
                    total_cost = root_cost + spur_cost
                    sig = tuple(e[2] for e in total_path)
                    if sig not in seen_B and sig not in seen_A:
                        counter += 1
                        heapq.heappush(B, (total_cost, counter, total_path))
                        seen_B.add(sig)

            found_next = False
            while B:
                c, _, next_path = heapq.heappop(B)
                sig = tuple(e[2] for e in next_path)
                if sig not in seen_A:
                    A.append(next_path)
                    seen_A.add(sig)
                    found_next = True
                    break

            if not found_next:
                break

        return A

    @classmethod
    def _assemble_candidate_from_edges(
        cls,
        graph: nx.MultiDiGraph,
        edge_path: List[Tuple[Any, Any, Any]],
        route_id: str,
        name: str,
    ) -> RouteCandidate:
        """
        Assemble a RouteCandidate directly from the exact (u, v, key) sequence
        selected by the pathfinding algorithm.
        """
        total_distance = 0.0
        total_eta = 0.0
        risk_scores = []
        combined_polyline = []
        segments_info = []

        for u, v, key in edge_path:
            edge = graph[u][v][key]

            dist = edge.get('distance_km', 0.0)
            eta = edge.get('base_travel_time_min', 0.0)
            risk = edge.get('risk_score', 0.0)

            total_distance += dist
            total_eta += eta
            risk_scores.append(risk)

            segments_info.append({
                'id': edge.get('id', key),
                'name': edge.get('name', ''),
                'length_km': dist,
                'risk_score': risk,
                'risk_level': edge.get('risk_level', 'low'),
                'status': edge.get('status', 'accessible'),
            })

            edge_coords = edge.get('coords', [])
            if edge_coords:
                if not combined_polyline:
                    combined_polyline.extend(edge_coords)
                else:
                    if combined_polyline[-1] == edge_coords[0]:
                        combined_polyline.extend(edge_coords[1:])
                    else:
                        combined_polyline.extend(edge_coords)

        # Route-level aggregate risk for API compatibility
        max_risk = max(risk_scores) if risk_scores else 0.0
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
        aggregate_risk = (0.7 * max_risk) + (0.3 * avg_risk)

        if aggregate_risk >= 66.0 or max_risk >= 80.0:
            risk_level = 'high'
        elif aggregate_risk >= 36.0 or max_risk >= 50.0:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return RouteCandidate(
            route_id=route_id,
            name=name,
            distance_km=round(total_distance, 2),
            base_eta_minutes=round(total_eta, 1),
            risk_score=round(aggregate_risk, 1),
            risk_level=risk_level,
            polyline=combined_polyline,
            segments=segments_info,
        )

    @classmethod
    def generate_candidate_routes(cls, origin_node: Any, dest_node: Any) -> List[RouteCandidate]:
        """
        Generate up to 3 distinct candidate routes between origin and destination nodes.
        Uses Yen's K-shortest simple paths on MultiDiGraph (K=3).
        Route diversity is strictly defined by distinct sequences of physical Infrastructure IDs.
        """
        graph = cls.get_graph()

        if origin_node not in graph or dest_node not in graph:
            raise ValueError(f"Origin '{origin_node}' or Destination '{dest_node}' not found in road network graph.")

        edge_paths = cls.find_k_shortest_paths(
            graph, origin_node, dest_node, K=3, weight='weight_distance'
        )

        if not edge_paths:
            raise ValueError(f"No navigable path found between '{origin_node}' and '{dest_node}'.")

        candidates = []
        for i, edge_path in enumerate(edge_paths):
            route_id = f'route-{i + 1}'
            name = f'Candidate Route {i + 1}'
            candidate = cls._assemble_candidate_from_edges(
                graph, edge_path, route_id=route_id, name=name
            )
            candidates.append(candidate)

        return candidates
