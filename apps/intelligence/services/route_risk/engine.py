"""
Route Risk Engine.

Evaluates route-level disruption risk from the infrastructure risks of the directed
road segments composing candidate routes.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from apps.intelligence.services.risk.config import RiskConfig, get_risk_config
from apps.intelligence.services.risk.engine import RiskEngine
from apps.intelligence.services.route_risk.aggregation import (
    aggregate_factors,
    build_route_explanation,
    calculate_length_weighted_score,
)
from apps.intelligence.services.route_risk.result import (
    RouteRiskResult,
    RouteSegmentRisk,
)
from apps.routes.models import Infrastructure

logger = logging.getLogger(__name__)


class RouteRiskEngine:
    """
    Evaluates explainable disruption risk across candidate routes.
    """

    @classmethod
    def resolve_segments(cls, route_input: Any) -> List[RouteSegmentRisk]:
        """
        Resolves various route representations into a normalized list of RouteSegmentRisk objects:
        - RouteCandidate instance
        - List of directed edge tuples: [(u, v, key), ...]
        - List/QuerySet of Infrastructure model instances
        - List of dictionary segments: [{'id': 1, ...}]
        """
        if route_input is None:
            return []

        # 1. RouteCandidate object (has .segments attribute)
        # 1. RouteCandidate object or dictionary with segments
        if hasattr(route_input, "segments") and isinstance(route_input.segments, list):
            return cls._resolve_from_segment_dicts(route_input.segments)
        if isinstance(route_input, dict) and isinstance(route_input.get("segments"), list):
            return cls._resolve_from_segment_dicts(route_input["segments"])

        # 2. Sequence of items
        if isinstance(route_input, (list, tuple)):
            if not route_input:
                return []
            first = route_input[0]

            # 2a. Directed MultiDiGraph edge tuples: (u, v, key)
            if isinstance(first, (tuple, list)) and len(first) >= 3:
                return cls._resolve_from_edges(route_input)

            # 2b. Infrastructure instances
            if isinstance(first, Infrastructure) or hasattr(first, "risk_score"):
                return cls._resolve_from_infrastructures(route_input)

            # 2c. Segment dictionaries
            if isinstance(first, dict):
                return cls._resolve_from_segment_dicts(route_input)

            # 2d. Integer Infrastructure IDs
            if isinstance(first, (int, str)) and str(first).isdigit():
                ids = [int(x) for x in route_input]
                infra_map = {inf.id: inf for inf in Infrastructure.objects.filter(id__in=ids)}
                return [
                    cls._infra_to_segment_risk(infra_map[i])
                    for i in ids
                    if i in infra_map
                ]

        # 3. QuerySet
        if hasattr(route_input, "all"):
            return cls._resolve_from_infrastructures(list(route_input.all()))

        logger.warning("Unrecognized route input type '%s'. Returning empty segments.", type(route_input))
        return []

    @classmethod
    def _resolve_from_edges(cls, edge_tuples: Sequence[Tuple[Any, Any, Any]]) -> List[RouteSegmentRisk]:
        """
        Resolves directed MultiDiGraph edges: (u, v, key) where key corresponds to Infrastructure.id.
        Preserves directed (u, v, key) edge identity.
        """
        keys = [e[2] for e in edge_tuples if len(e) >= 3]
        valid_int_keys = [k for k in keys if isinstance(k, int) or (isinstance(k, str) and k.isdigit())]
        
        infra_map = {}
        if valid_int_keys:
            infra_map = {
                inf.id: inf
                for inf in Infrastructure.objects.filter(id__in=[int(k) for k in valid_int_keys])
            }

        segments = []
        for edge in edge_tuples:
            u, v, key = edge[0], edge[1], edge[2]
            int_key = int(key) if isinstance(key, int) or (isinstance(key, str) and key.isdigit()) else None

            if int_key and int_key in infra_map:
                infra = infra_map[int_key]
                seg = cls._infra_to_segment_risk(infra, edge_identity=(u, v, key))
            else:
                # Fallback if not found in DB
                seg = RouteSegmentRisk(
                    infrastructure_id=int_key or 0,
                    name=f"Segment ({u}->{v} #{key})",
                    edge_identity=(u, v, key),
                    length_km=0.0,
                    risk_score=0.0,
                    risk_level="low",
                    top_factors=[],
                )
            segments.append(seg)

        return segments

    @classmethod
    def _resolve_from_infrastructures(
        cls, infrastructures: Iterable[Infrastructure]
    ) -> List[RouteSegmentRisk]:
        return [cls._infra_to_segment_risk(inf) for inf in infrastructures]

    @classmethod
    def _resolve_from_segment_dicts(cls, segment_dicts: List[Dict[str, Any]]) -> List[RouteSegmentRisk]:
        """
        Resolves segment dictionaries. Queries persisted DB attributes if factors/details are missing.
        """
        needed_ids = [
            s.get("id") or s.get("infrastructure_id")
            for s in segment_dicts
            if (s.get("id") or s.get("infrastructure_id")) and "top_factors" not in s
        ]
        
        infra_map = {}
        if needed_ids:
            infra_map = {
                inf.id: inf
                for inf in Infrastructure.objects.filter(id__in=needed_ids)
            }

        segments = []
        for s in segment_dicts:
            infra_id = s.get("id") or s.get("infrastructure_id") or 0
            infra = infra_map.get(infra_id)

            if infra:
                seg = cls._infra_to_segment_risk(infra)
                # Override length if provided in dict
                if "length_km" in s and s["length_km"] is not None:
                    seg.length_km = float(s["length_km"])
                if "risk_score" in s and s["risk_score"] is not None:
                    seg.risk_score = float(s["risk_score"])
                if "risk_level" in s and s["risk_level"]:
                    seg.risk_level = str(s["risk_level"]).lower()
            else:
                seg = RouteSegmentRisk(
                    infrastructure_id=infra_id,
                    name=s.get("name") or f"Segment #{infra_id}",
                    edge_identity=s.get("edge_identity"),
                    length_km=float(s.get("length_km", 0.0) or 0.0),
                    risk_score=float(s.get("risk_score", 0.0) or 0.0),
                    risk_level=s.get("risk_level", "low").lower(),
                    top_factors=s.get("top_factors", []),
                )
            segments.append(seg)

        return segments

    @classmethod
    def _infra_to_segment_risk(
        cls, infra: Infrastructure, edge_identity: Optional[Tuple[Any, Any, Any]] = None
    ) -> RouteSegmentRisk:
        return RouteSegmentRisk(
            infrastructure_id=infra.id,
            name=infra.name or f"Segment #{infra.id}",
            edge_identity=edge_identity,
            length_km=float(infra.length_km or 0.0),
            risk_score=float(infra.risk_score or 0.0),
            risk_level=str(infra.risk_level or "low").lower(),
            top_factors=list(infra.top_factors or []),
        )

    @classmethod
    def assess_route(
        cls,
        route_input: Any,
        config: Optional[RiskConfig] = None,
    ) -> RouteRiskResult:
        """
        Assess route disruption risk from candidate route input.
        """
        active_config = config or get_risk_config()
        segments = cls.resolve_segments(route_input)

        if not segments:
            return RouteRiskResult(
                route_score=0.0,
                route_level="low",
                max_segment_score=0.0,
                highest_risk_segments=[],
                segment_count=0,
                high_risk_segment_count=0,
                medium_risk_segment_count=0,
                low_risk_segment_count=0,
                total_length_km=0.0,
                segments=[],
                factor_summary=[],
                explanation="Empty route: no road segments to evaluate.",
            )

        # 1. Length-weighted score aggregation
        route_score = calculate_length_weighted_score(segments)
        route_level = RiskEngine.classify_risk_level(route_score, active_config)

        # 2. Risk breakdown metrics
        total_length = sum(s.length_km for s in segments)
        max_segment_score = max(s.risk_score for s in segments) if segments else 0.0
        highest_risk_segments = [s for s in segments if s.risk_score == max_segment_score and max_segment_score > 0]

        high_count = sum(1 for s in segments if s.risk_level == "high" or s.risk_score > active_config.threshold_medium_max)
        med_count = sum(1 for s in segments if (s.risk_level == "medium" or active_config.threshold_low_max < s.risk_score <= active_config.threshold_medium_max) and s not in highest_risk_segments)
        # Recount cleanly based on thresholds
        high_risk_segment_count = sum(1 for s in segments if s.risk_score > active_config.threshold_medium_max)
        medium_risk_segment_count = sum(1 for s in segments if active_config.threshold_low_max < s.risk_score <= active_config.threshold_medium_max)
        low_risk_segment_count = sum(1 for s in segments if s.risk_score <= active_config.threshold_low_max)

        # 3. Aggregated factor breakdown
        factor_summary = aggregate_factors(segments)

        # 4. Human-readable explanation
        explanation = build_route_explanation(
            route_score=route_score,
            route_level=route_level,
            max_segment_score=max_segment_score,
            high_risk_count=high_risk_segment_count,
            medium_risk_count=medium_risk_segment_count,
            total_segments=len(segments),
            factor_summary=factor_summary,
        )

        return RouteRiskResult(
            route_score=route_score,
            route_level=route_level,
            max_segment_score=max_segment_score,
            highest_risk_segments=highest_risk_segments,
            segment_count=len(segments),
            high_risk_segment_count=high_risk_segment_count,
            medium_risk_segment_count=medium_risk_segment_count,
            low_risk_segment_count=low_risk_segment_count,
            total_length_km=round(total_length, 2),
            segments=segments,
            factor_summary=factor_summary,
            explanation=explanation,
        )
