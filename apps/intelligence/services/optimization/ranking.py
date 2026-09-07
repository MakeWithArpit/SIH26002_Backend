"""
Normalization, Deterministic Ranking, and Explainability for Route Optimization.
"""
from typing import Any, List, Optional, Sequence, Tuple

from apps.intelligence.services.optimization.config import OptimizationConfig
from apps.intelligence.services.optimization.result import (
    OptimizedRouteCandidate,
    RouteOptimizationResult,
)
from apps.intelligence.services.route_risk.result import RouteRiskResult


def get_candidate_distance(route: Any) -> float:
    """
    Extract route distance in kilometers from candidate route object or dict.
    """
    if hasattr(route, "distance_km"):
        return float(route.distance_km or 0.0)
    if isinstance(route, dict):
        return float(route.get("distance_km", 0.0) or 0.0)
    return 0.0


def get_candidate_id(route: Any, fallback_index: int = 1) -> str:
    """
    Extract route ID from candidate route object or dict.
    """
    if hasattr(route, "route_id") and route.route_id:
        return str(route.route_id)
    if isinstance(route, dict) and route.get("route_id"):
        return str(route.get("route_id"))
    return f"route-{fallback_index}"


def get_candidate_name(route: Any, fallback_index: int = 1) -> str:
    """
    Extract route name from candidate route object or dict.
    """
    if hasattr(route, "name") and route.name:
        return str(route.name)
    if isinstance(route, dict) and route.get("name"):
        return str(route.get("name"))
    return f"Candidate Route {fallback_index}"


def normalize_and_score_candidates(
    evaluated_candidates: Sequence[Tuple[Any, RouteRiskResult, int]],
    config: OptimizationConfig,
) -> List[OptimizedRouteCandidate]:
    """
    Normalizes distance and risk across the COMPLETE candidate set and calculates
    full-precision optimization cost.

    Does not round optimization_cost before ranking.
    """
    if not evaluated_candidates:
        return []

    distances = [get_candidate_distance(route) for route, _, _ in evaluated_candidates]
    max_distance = max(distances) if distances else 0.0

    w_dist = config.normalized_distance_weight
    w_risk = config.normalized_risk_weight

    optimized_list: List[OptimizedRouteCandidate] = []

    for route, route_risk, original_idx in evaluated_candidates:
        dist = get_candidate_distance(route)

        # Distance normalization across the complete candidate set
        if max_distance <= 0.0:
            d_norm = 0.0
        else:
            d_norm = min(max(dist / max_distance, 0.0), 1.0)

        # Risk normalization from 0-100 scale
        r_norm = min(max(route_risk.route_score / 100.0, 0.0), 1.0)

        # Optimization cost calculated with full floating-point precision
        cost = min(max((w_dist * d_norm) + (w_risk * r_norm), 0.0), 1.0)

        optimized_list.append(
            OptimizedRouteCandidate(
                route=route,
                route_risk=route_risk,
                distance_normalized=d_norm,
                risk_normalized=r_norm,
                optimization_cost=cost,
                original_index=original_idx,
            )
        )

    return optimized_list


def rank_candidates(
    candidates: List[OptimizedRouteCandidate],
) -> List[OptimizedRouteCandidate]:
    """
    Deterministically ranks candidates using full precision:
    1. Lowest optimization_cost (ascending)
    2. Lower route_risk score (ascending)
    3. Shorter distance_km (ascending)
    4. Stable original candidate index (ascending)
    """
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            c.optimization_cost,
            c.route_risk.route_score,
            get_candidate_distance(c.route),
            c.original_index,
        ),
    )

    for i, c in enumerate(sorted_candidates):
        c.rank = i + 1
        c.is_selected = (i == 0)

    return sorted_candidates


def build_explanations(
    ranked_candidates: List[OptimizedRouteCandidate],
) -> Tuple[str, List[OptimizedRouteCandidate]]:
    """
    Generates transparent, quantitative explanations for the overall optimization
    result and each individual candidate.
    """
    if not ranked_candidates:
        return "No candidate routes provided for optimization.", []

    if len(ranked_candidates) == 1:
        sel = ranked_candidates[0]
        r_id = get_candidate_id(sel.route, 1)
        dist = get_candidate_distance(sel.route)
        score = sel.route_risk.route_score
        level = sel.route_risk.route_level.upper()

        overall_explanation = (
            f"Route {r_id} selected as the only available candidate route "
            f"(distance: {dist:.1f} km, disruption risk: {score:.1f}/100 [{level}])."
        )
        sel.explanation = overall_explanation
        return overall_explanation, ranked_candidates

    selected = ranked_candidates[0]
    sel_id = get_candidate_id(selected.route, 1)
    sel_dist = get_candidate_distance(selected.route)
    sel_score = selected.route_risk.route_score
    sel_level = selected.route_risk.route_level.upper()
    sel_cost = selected.optimization_cost

    # Find the shortest alternative to determine if selected route is a detour
    shortest_cand = min(ranked_candidates, key=lambda c: get_candidate_distance(c.route))
    shortest_id = get_candidate_id(shortest_cand.route, 1)
    shortest_dist = get_candidate_distance(shortest_cand.route)
    shortest_score = shortest_cand.route_risk.route_score
    shortest_level = shortest_cand.route_risk.route_level.upper()

    dist_diff = sel_dist - shortest_dist
    risk_diff = shortest_score - sel_score

    if selected != shortest_cand and dist_diff > 0.1 and risk_diff > 0.0:
        overall_explanation = (
            f"Route {sel_id} selected despite being {dist_diff:.1f} km longer "
            f"because its disruption risk ({sel_score:.1f}/100 [{sel_level}]) is substantially lower "
            f"than {shortest_id} ({shortest_score:.1f}/100 [{shortest_level}]), "
            f"achieving the lowest optimization cost ({sel_cost:.4f})."
        )
    elif selected == shortest_cand and sel_score <= min(c.route_risk.route_score for c in ranked_candidates):
        overall_explanation = (
            f"Route {sel_id} selected as it provides both the shortest distance ({sel_dist:.1f} km) "
            f"and lowest disruption risk ({sel_score:.1f}/100 [{sel_level}]) with an optimization cost of {sel_cost:.4f}."
        )
    else:
        overall_explanation = (
            f"Route {sel_id} selected because it provides the lowest combined optimization cost ({sel_cost:.4f}), "
            f"optimally balancing distance ({sel_dist:.1f} km) and disruption risk ({sel_score:.1f}/100 [{sel_level}])."
        )

    # Candidate-level explanations
    for c in ranked_candidates:
        c_id = get_candidate_id(c.route, c.rank)
        c_dist = get_candidate_distance(c.route)
        c_score = c.route_risk.route_score
        c_level = c.route_risk.route_level.upper()
        c_cost = c.optimization_cost

        if c.is_selected:
            c.explanation = (
                f"Selected optimal route (rank {c.rank}): lowest optimization cost {c_cost:.4f} "
                f"(distance: {c_dist:.1f} km, disruption risk: {c_score:.1f}/100 [{c_level}])."
            )
        else:
            c.explanation = (
                f"Alternative route (rank {c.rank}): optimization cost {c_cost:.4f} "
                f"(distance: {c_dist:.1f} km, disruption risk: {c_score:.1f}/100 [{c_level}])."
            )

    return overall_explanation, ranked_candidates

