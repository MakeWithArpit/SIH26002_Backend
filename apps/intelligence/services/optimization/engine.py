"""
Route Optimization Engine.

Selects the preferred route from candidate routes by balancing route efficiency (distance)
and route disruption risk (evaluated via RouteRiskEngine).
"""
import logging
from typing import Any, List, Optional, Sequence, Tuple

from apps.intelligence.services.optimization.config import (
    OptimizationConfig,
    get_optimization_config,
)
from apps.intelligence.services.optimization.ranking import (
    build_explanations,
    normalize_and_score_candidates,
    rank_candidates,
)
from apps.intelligence.services.optimization.result import (
    OptimizedRouteCandidate,
    RouteOptimizationResult,
)
from apps.intelligence.services.route_risk.engine import RouteRiskEngine
from apps.intelligence.services.route_risk.result import RouteRiskResult

logger = logging.getLogger(__name__)


class RouteOptimizationEngine:
    """
    Ranks and selects optimal routes across candidate paths based on distance cost
    and disruption risk.
    """

    @classmethod
    def optimize_routes(
        cls,
        candidates: Sequence[Any],
        config: Optional[OptimizationConfig] = None,
    ) -> RouteOptimizationResult:
        """
        Evaluate and rank candidate routes.

        Args:
            candidates: Sequence of RouteCandidate objects, edge lists, or route dicts.
            config: Optional OptimizationConfig. If None, loaded from Django settings.

        Returns:
            RouteOptimizationResult containing the selected route and full ranked list.
        """
        if not candidates:
            return RouteOptimizationResult(
                selected_route=None,
                selected_route_risk=None,
                ranked_candidates=[],
                candidate_count=0,
                explanation="No candidate routes provided for optimization.",
            )

        active_config = config or get_optimization_config()

        # Step 1: Assess route disruption risk via canonical RouteRiskEngine
        evaluated_candidates: List[Tuple[Any, RouteRiskResult, int]] = []
        for idx, candidate in enumerate(candidates):
            route_risk = RouteRiskEngine.assess_route(candidate)
            evaluated_candidates.append((candidate, route_risk, idx))

        # Step 2: Set-wide normalization and full-precision cost calculation
        scored_candidates = normalize_and_score_candidates(
            evaluated_candidates, config=active_config
        )

        # Step 3: Deterministic ranking with tie-breaking
        ranked_candidates = rank_candidates(scored_candidates)

        # Step 4: Explainability generation
        overall_explanation, explained_candidates = build_explanations(ranked_candidates)

        selected_route = explained_candidates[0] if explained_candidates else None
        selected_route_risk = selected_route.route_risk if selected_route else None

        return RouteOptimizationResult(
            selected_route=selected_route,
            selected_route_risk=selected_route_risk,
            ranked_candidates=explained_candidates,
            candidate_count=len(explained_candidates),
            explanation=overall_explanation,
        )

