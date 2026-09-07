"""
Aggregation algorithms and factor summarization for Route Risk Engine.
"""
from typing import List, Dict, Any
from apps.intelligence.services.route_risk.result import RouteSegmentRisk, FactorContributionSummary


CANONICAL_FACTORS = [
    "landslide_susceptibility",
    "historical_landslide",
    "recent_rainfall",
    "flood_hazard",
    "weather_warning",
]


def calculate_length_weighted_score(segments: List[RouteSegmentRisk]) -> float:
    """
    Calculates the primary route disruption risk score.

    Uses length-weighted average:
        route_score = sum(segment_score * segment_length) / sum(segment_length)

    Falls back to unweighted arithmetic mean if segment lengths are unavailable or sum to 0.
    Clamps final score to [0.0, 100.0].
    """
    if not segments:
        return 0.0

    valid_lengths = [s.length_km for s in segments if s.length_km and s.length_km > 0]
    total_length = sum(valid_lengths)

    if total_length > 0:
        weighted_sum = sum(s.risk_score * s.length_km for s in segments)
        raw_score = weighted_sum / total_length
    else:
        # Fallback to arithmetic mean
        raw_score = sum(s.risk_score for s in segments) / len(segments)

    clamped_score = round(min(100.0, max(0.0, raw_score)), 1)
    return clamped_score


def aggregate_factors(segments: List[RouteSegmentRisk]) -> List[FactorContributionSummary]:
    """
    Aggregates factor contributions across all route segments.
    Preserves canonical factor names from Phase 7 risk engine.
    """
    if not segments:
        return []

    summaries = []
    for factor_name in CANONICAL_FACTORS:
        total_contrib = 0.0
        affected_count = 0
        max_contrib = 0.0

        for segment in segments:
            for factor in segment.top_factors:
                if factor.get("name") == factor_name:
                    contrib = float(factor.get("contribution", 0.0) or 0.0)
                    if contrib > 0:
                        total_contrib += contrib
                        affected_count += 1
                        if contrib > max_contrib:
                            max_contrib = contrib

        human_name = factor_name.replace("_", " ").title()
        if affected_count > 0:
            desc = f"{human_name} impacts {affected_count}/{len(segments)} segment(s) (peak segment contribution: +{max_contrib:.1f})"
        else:
            desc = f"No {human_name} disruption detected along route"

        summaries.append(
            FactorContributionSummary(
                factor_name=factor_name,
                total_contribution=round(total_contrib, 2),
                affected_segments_count=affected_count,
                max_single_contribution=round(max_contrib, 2),
                description=desc,
            )
        )

    return summaries


def build_route_explanation(
    route_score: float,
    route_level: str,
    max_segment_score: float,
    high_risk_count: int,
    medium_risk_count: int,
    total_segments: int,
    factor_summary: List[FactorContributionSummary],
) -> str:
    """
    Generates a clear, human-readable explanation of the route-level risk.
    """
    if total_segments == 0:
        return "Empty route with 0 segments evaluated."

    parts = [
        f"Route classified as {route_level.upper()} risk (score: {route_score:.1f}/100 across {total_segments} segment(s))."
    ]

    if high_risk_count > 0:
        parts.append(f"Contains {high_risk_count} high-risk bottleneck segment(s) (peak segment risk: {max_segment_score:.1f}/100).")
    elif medium_risk_count > 0:
        parts.append(f"Contains {medium_risk_count} moderate-risk segment(s) (peak segment risk: {max_segment_score:.1f}/100).")
    else:
        parts.append("All segments exhibit low baseline disruption risk.")

    active_factors = [f for f in factor_summary if f.affected_segments_count > 0]
    if active_factors:
        factor_descs = [f"{f.factor_name.replace('_', ' ')} (+{f.max_single_contribution:.1f} peak)" for f in active_factors]
        parts.append("Primary hazard driver(s): " + ", ".join(factor_descs) + ".")

    return " ".join(parts)
