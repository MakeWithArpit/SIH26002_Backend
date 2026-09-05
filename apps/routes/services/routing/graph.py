"""
Road Network Graph Service — NetworkX pathfinding on PostGIS Infrastructure.

Builds graph from Infrastructure segments and calculates:
1. Shortest Path (pure distance/travel time)
2. Safest Path (risk-penalized edge weights)
Produces ephemeral RouteCandidate objects (never stored in DB).
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
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
    @classmethod
    def build_graph(cls) -> nx.Graph:
        """
        Construct a NetworkX graph from all active Infrastructure segments.
        """
        graph = nx.Graph()
        infrastructures = Infrastructure.objects.select_related('district').all()

        for infra in infrastructures:
            # Edge weight for safest path calculation
            # Multiplier increases drastically with risk score
            # Score 0 -> mult 1.0; Score 50 -> mult 4.3; Score 90 -> mult 7.0
            risk_multiplier = 1.0 + (infra.risk_score / 15.0)
            if infra.status == 'blocked':
                risk_multiplier *= 100.0

            safest_weight = infra.length_km * risk_multiplier

            # PostGIS coords to lat/lng list [[lat, lng], ...]
            coords = []
            if infra.geom:
                coords = [[pt[1], pt[0]] for pt in infra.geom.coords]

            edge_data = {
                'id': infra.id,
                'name': infra.name,
                'infra_type': infra.infra_type,
                'road_classification': infra.road_classification,
                'length_km': infra.length_km,
                'base_travel_time_min': infra.base_travel_time_min,
                'risk_score': infra.risk_score,
                'risk_level': infra.risk_level,
                'status': infra.status,
                'coords': coords,
                'weight_distance': infra.length_km,
                'weight_safest': safest_weight,
            }

            graph.add_edge(infra.start_node, infra.end_node, **edge_data)

        return graph

    @classmethod
    def find_nearest_node(cls, lat: float, lng: float) -> Optional[str]:
        """
        Find the closest road graph node to the given coordinates.
        """
        point = Point(lng, lat, srid=4326)
        nearest_infra = Infrastructure.objects.annotate(
            dist=Distance('geom', point)
        ).order_by('dist').first()

        if not nearest_infra or not nearest_infra.geom:
            return None

        # Compare distance from point to start vs end coordinate of the LineString
        coords = nearest_infra.geom.coords
        start_pt = Point(coords[0][0], coords[0][1], srid=4326)
        end_pt = Point(coords[-1][0], coords[-1][1], srid=4326)

        dist_to_start = point.distance(start_pt)
        dist_to_end = point.distance(end_pt)

        return nearest_infra.start_node if dist_to_start <= dist_to_end else nearest_infra.end_node

    @classmethod
    def _assemble_route(cls, graph: nx.Graph, path_nodes: List[str], route_id: str, name: str) -> RouteCandidate:
        """
        Assemble a RouteCandidate from an ordered sequence of node IDs.
        """
        total_distance = 0.0
        total_eta = 0.0
        risk_scores = []
        combined_polyline = []
        segments_info = []

        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            edge = graph[u][v]

            total_distance += edge.get('length_km', 0.0)
            total_eta += edge.get('base_travel_time_min', 0.0)
            risk_scores.append(edge.get('risk_score', 0.0))

            segments_info.append({
                'id': edge.get('id'),
                'name': edge.get('name'),
                'length_km': edge.get('length_km'),
                'risk_score': edge.get('risk_score'),
                'risk_level': edge.get('risk_level'),
                'status': edge.get('status'),
            })

            edge_coords = edge.get('coords', [])
            if edge_coords:
                # If first segment, add all coords; else skip first to avoid duplicate node
                if not combined_polyline:
                    combined_polyline.extend(edge_coords)
                else:
                    combined_polyline.extend(edge_coords[1:])

        # Route-level aggregate risk
        max_risk = max(risk_scores) if risk_scores else 0.0
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
        # Weighted aggregate risk (70% max segment risk + 30% average)
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
            distance_km=total_distance,
            base_eta_minutes=total_eta,
            risk_score=aggregate_risk,
            risk_level=risk_level,
            polyline=combined_polyline,
            segments=segments_info,
        )

    @classmethod
    def generate_candidate_routes(cls, origin_node: str, dest_node: str) -> List[RouteCandidate]:
        """
        Generate candidate routes between origin and destination nodes.
        Returns:
        - Candidate 1: Shortest Path (by distance)
        - Candidate 2: Safest Path (risk-penalized edge weights)
        - Candidate 3: Alternative Path (if distinctly available)
        """
        graph = cls.build_graph()

        if origin_node not in graph or dest_node not in graph:
            raise ValueError(f"Origin '{origin_node}' or Destination '{dest_node}' not found in road network graph.")

        if not nx.has_path(graph, origin_node, dest_node):
            raise ValueError(f"No navigable path found between '{origin_node}' and '{dest_node}'.")

        candidates = []

        # 1. Shortest path (distance)
        shortest_path = nx.shortest_path(graph, origin_node, dest_node, weight='weight_distance')
        candidate_shortest = cls._assemble_route(
            graph,
            shortest_path,
            route_id='route-shortest',
            name='Direct Highway Route (Shortest)',
        )
        candidates.append(candidate_shortest)

        # 2. Safest path (risk-penalized)
        safest_path = nx.shortest_path(graph, origin_node, dest_node, weight='weight_safest')
        if safest_path != shortest_path:
            candidate_safest = cls._assemble_route(
                graph,
                safest_path,
                route_id='route-safe',
                name='Low-Risk Alternative Route (Safest)',
            )
            candidates.append(candidate_safest)

        # 3. If shortest and safest are the same, try finding a 2nd alternative path via shortest_simple_paths
        if len(candidates) == 1:
            try:
                paths_gen = nx.shortest_simple_paths(graph, origin_node, dest_node, weight='weight_distance')
                for i, alt_path in enumerate(paths_gen):
                    if i == 0:
                        continue  # skip shortest which we already have
                    candidate_alt = cls._assemble_route(
                        graph,
                        alt_path,
                        route_id=f'route-alt-{i}',
                        name=f'Alternative Route {i}',
                    )
                    candidates.append(candidate_alt)
                    if len(candidates) >= 2:
                        break
            except Exception as e:
                logger.debug("No additional alternative simple paths: %s", e)

        return candidates
