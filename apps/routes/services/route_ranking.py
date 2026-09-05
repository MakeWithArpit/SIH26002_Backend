"""
AI-03 Route Ranking & Recommendation Service.

Evaluates candidate routes, weighs distance vs disruption risk,
selects the recommended route, and generates transparent explanations.
"""
from typing import List
from apps.routes.services.routing.graph import RouteCandidate


class RouteRankingService:
    @classmethod
    def rank_routes(cls, candidates: List[RouteCandidate]) -> List[RouteCandidate]:
        if not candidates:
            return []

        if len(candidates) == 1:
            candidates[0].recommended = True
            candidates[0].explanation = "Only navigable route available between origin and destination."
            return candidates

        shortest = next((c for c in candidates if c.route_id == 'route-shortest'), candidates[0])
        safest = next((c for c in candidates if c.route_id == 'route-safe'), None)

        if safest and safest != shortest:
            risk_diff = shortest.risk_score - safest.risk_score
            dist_diff = round(safest.distance_km - shortest.distance_km, 1)
            time_diff = round(safest.base_eta_minutes - shortest.base_eta_minutes, 1)

            # Recommend safest route if shortest has high risk (or risk >= 45) and safest provides meaningful safety improvement
            if (shortest.risk_level == 'high' or shortest.risk_score >= 45.0) and risk_diff >= 15.0:
                safest.recommended = True
                safest.explanation = (
                    f"Recommended for safety: Avoids high-risk road segments. "
                    f"Adds {dist_diff} km (+{time_diff} mins) to bypass severe hazard zones "
                    f"with a {round(risk_diff, 1)} points lower risk score."
                )
                shortest.recommended = False
                shortest.explanation = (
                    f"Direct shortest route, but NOT recommended due to {shortest.risk_level.upper()} "
                    f"disruption risk (score {round(shortest.risk_score, 1)}/100)."
                )
            else:
                shortest.recommended = True
                shortest.explanation = (
                    f"Recommended: Shortest direct route with acceptable risk profile "
                    f"({shortest.risk_level.upper()} - {round(shortest.risk_score, 1)}/100)."
                )
                safest.recommended = False
                safest.explanation = (
                    f"Alternative route available ({dist_diff} km longer, +{time_diff} mins)."
                )

            # Sort so recommended route is always first
            return sorted(candidates, key=lambda c: (not c.recommended, c.risk_score))

        # Default fallback if only simple paths
        candidates[0].recommended = True
        candidates[0].explanation = "Optimal route based on road network features."
        return candidates
