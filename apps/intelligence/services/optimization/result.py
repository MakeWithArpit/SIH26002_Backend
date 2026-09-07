"""
Result Dataclasses for Route Optimization Engine.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.intelligence.services.route_risk.result import RouteRiskResult


@dataclass
class OptimizedRouteCandidate:
    """
    Candidate route enriched with disruption risk assessment, normalized metrics,
    full-precision optimization cost, and ranking.
    """
    route: Any
    route_risk: RouteRiskResult
    distance_normalized: float
    risk_normalized: float
    optimization_cost: float
    rank: int = 0
    is_selected: bool = False
    explanation: str = ""
    original_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize candidate to dictionary with presentation rounding.
        """
        route_data = self.route.to_dict() if hasattr(self.route, "to_dict") else self.route

        return {
            "route": route_data,
            "route_risk": self.route_risk.to_dict() if hasattr(self.route_risk, "to_dict") else self.route_risk,
            "distance_normalized": round(self.distance_normalized, 4),
            "risk_normalized": round(self.risk_normalized, 4),
            "optimization_cost": round(self.optimization_cost, 4),
            "rank": self.rank,
            "is_selected": self.is_selected,
            "explanation": self.explanation,
        }


@dataclass
class RouteOptimizationResult:
    """
    Complete result of the Route Optimization Engine.
    """
    selected_route: Optional[OptimizedRouteCandidate]
    selected_route_risk: Optional[RouteRiskResult]
    ranked_candidates: List[OptimizedRouteCandidate] = field(default_factory=list)
    candidate_count: int = 0
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize optimization result to dictionary for API responses.
        """
        return {
            "selected_route": self.selected_route.to_dict() if self.selected_route else None,
            "selected_route_risk": self.selected_route_risk.to_dict() if self.selected_route_risk else None,
            "ranked_candidates": [c.to_dict() for c in self.ranked_candidates],
            "candidate_count": self.candidate_count,
            "explanation": self.explanation,
        }

