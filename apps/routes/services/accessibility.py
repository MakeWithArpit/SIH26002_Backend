"""
Phase 10 — Accessibility Intelligence: AccessibilityService

Replaces static District.accessibility_score with a dynamic, multi-component
score computed from live infrastructure and weather data.

Score range: 0.0 (inaccessible) → 10.0 (fully accessible)

Weight breakdown:
  - Road condition score    40%
  - Infrastructure risk     30%
  - Connectivity status     20%
  - Weather penalty         10%
"""
import logging
from typing import Dict, Any

from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.routes.models import (
    District,
    Infrastructure,
    OperationalStatus,
    PhysicalCondition,
    ConnectivityStatus,
    WeatherCondition,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score lookup tables
# ---------------------------------------------------------------------------

CONDITION_SCORES: Dict[str, float] = {
    PhysicalCondition.GOOD: 10.0,
    PhysicalCondition.MODERATE: 7.0,
    PhysicalCondition.POOR: 4.0,
    PhysicalCondition.DAMAGED: 1.0,
}

STATUS_PENALTIES: Dict[str, float] = {
    OperationalStatus.ACCESSIBLE: 0.0,
    OperationalStatus.RISKY: 2.0,
    OperationalStatus.BLOCKED: 5.0,
}

CONNECTIVITY_SCORES: Dict[str, float] = {
    ConnectivityStatus.NORMAL: 10.0,
    ConnectivityStatus.DEGRADED: 5.0,
    ConnectivityStatus.CRITICAL: 1.0,
}

WEATHER_PENALTIES: Dict[str, float] = {
    WeatherCondition.CLEAR: 0.0,
    WeatherCondition.MODERATE: 1.0,
    WeatherCondition.HEAVY: 2.5,
    WeatherCondition.EXTREME: 7.0,
}

# Weight configuration (must sum to 1.0)
WEIGHTS = {
    'road_condition': 0.40,
    'risk': 0.30,
    'connectivity': 0.20,
    'weather': 0.10,
}


class AccessibilityService:
    """
    Dynamic accessibility intelligence for a District.

    Usage:
        service = AccessibilityService()
        score, breakdown = service.compute_district_score(district)
        service.compute_all_districts()  # batch update
    """

    def compute_district_score(self, district: District) -> Dict[str, Any]:
        """
        Compute accessibility score + component breakdown for one district.

        Returns:
            {
              'score': 7.4,
              'components': {
                  'road_condition_score': 8.5,
                  'risk_score': 6.0,
                  'connectivity_score': 10.0,
                  'weather_score': 8.0,
              },
              'weights': { ... },
              'segment_count': 12,
              'blocked_count': 0,
              'computed_at': '...',
            }
        """
        infra_qs = district.infrastructure.all()

        # ── Component 1: Road Condition (40%) ──────────────────────────────
        road_condition_score = self._compute_road_condition_score(infra_qs)

        # ── Component 2: Infrastructure Risk (30%) ─────────────────────────
        risk_component_score = self._compute_risk_score(infra_qs)

        # ── Component 3: Connectivity Status (20%) ─────────────────────────
        connectivity_score = CONNECTIVITY_SCORES.get(
            district.connectivity_status, 5.0
        )

        # ── Component 4: Weather Penalty (10%) ────────────────────────────
        weather_score = self._compute_weather_score(district)

        # ── Weighted aggregate ─────────────────────────────────────────────
        total_score = round(
            road_condition_score * WEIGHTS['road_condition']
            + risk_component_score * WEIGHTS['risk']
            + connectivity_score * WEIGHTS['connectivity']
            + weather_score * WEIGHTS['weather'],
            2,
        )
        total_score = max(0.0, min(10.0, total_score))

        # Counts for context
        total = infra_qs.count()
        blocked = infra_qs.filter(status=OperationalStatus.BLOCKED).count()

        return {
            'score': total_score,
            'components': {
                'road_condition_score': road_condition_score,
                'risk_score': risk_component_score,
                'connectivity_score': connectivity_score,
                'weather_score': weather_score,
            },
            'weights': WEIGHTS,
            'segment_count': total,
            'blocked_count': blocked,
            'computed_at': timezone.now().isoformat(),
        }

    def compute_all_districts(self) -> Dict[str, Any]:
        """
        Recompute accessibility_score for every District and persist it.

        Returns summary: { 'updated': N, 'districts': [ { id, name, score } ] }
        """
        updated = []
        for district in District.objects.all():
            try:
                result = self.compute_district_score(district)
                new_score = result['score']
                District.objects.filter(pk=district.pk).update(
                    accessibility_score=new_score
                )
                updated.append({
                    'id': district.pk,
                    'name': district.name,
                    'score': new_score,
                })
                logger.debug(
                    'Accessibility updated district=%s score=%.2f', district.name, new_score
                )
            except Exception as exc:
                logger.error(
                    'AccessibilityService error for district=%s: %s', district.name, exc
                )

        logger.info('AccessibilityService computed %d districts.', len(updated))
        return {'updated': len(updated), 'districts': updated}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_road_condition_score(self, infra_qs) -> float:
        """
        Average road condition score across all segments, penalised by
        operational status.
        """
        segments = infra_qs.values('condition', 'status')
        if not segments.exists():
            return 5.0  # neutral default for empty district

        total, count = 0.0, 0
        for seg in segments:
            base = CONDITION_SCORES.get(seg['condition'], 5.0)
            penalty = STATUS_PENALTIES.get(seg['status'], 0.0)
            total += max(0.0, base - penalty)
            count += 1

        return round(total / count, 2) if count > 0 else 5.0

    def _compute_risk_score(self, infra_qs) -> float:
        """
        Convert average infrastructure risk_score (0–100) to a 0–10 accessibility
        component. Higher risk → lower accessibility.
        """
        agg = infra_qs.aggregate(avg_risk=Avg('risk_score'))
        avg_risk = agg['avg_risk'] or 0.0
        # Invert: risk 0 → score 10, risk 100 → score 0
        return round(max(0.0, 10.0 - (avg_risk / 10.0)), 2)

    def _compute_weather_score(self, district: District) -> float:
        """
        Derive a weather accessibility score from the latest weather snapshot.
        Higher rainfall / worse condition → lower score.
        """
        latest = district.latest_weather
        if not latest:
            return 10.0  # no data → assume clear

        base_penalty = WEATHER_PENALTIES.get(latest.condition, 0.0)

        # Additional rainfall penalty: every 20mm above 50mm costs 0.5 points
        rainfall_penalty = max(0.0, (latest.rainfall_mm - 50.0) / 20.0) * 0.5

        score = max(0.0, 10.0 - base_penalty - rainfall_penalty)
        return round(score, 2)
