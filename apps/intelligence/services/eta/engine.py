"""
ETA Estimation Engine.

Practical, deterministic, explainable travel time and delay calculation.
"""
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from apps.intelligence.services.eta.adjustments import (
    calculate_base_travel_time,
    calculate_segment_risk_adjustments,
    calculate_telemetry_adjustment,
    calculate_weather_adjustment,
    classify_delay_severity,
)
from apps.intelligence.services.eta.config import ETAConfig, get_eta_config
from apps.intelligence.services.eta.result import (
    ETAFactorAdjustment,
    ETAResult,
)
from apps.intelligence.services.route_risk.engine import RouteRiskEngine
from apps.intelligence.services.route_risk.result import RouteRiskResult, RouteSegmentRisk

logger = logging.getLogger(__name__)


class ETAEngine:
    """
    Evaluates condition-adjusted travel time and expected delays for route candidates.
    """

    @classmethod
    def estimate_eta(
        cls,
        candidate: Any,
        route_risk: Optional[RouteRiskResult] = None,
        weather_snapshot: Optional[Any] = None,
        rainfall_mm: Optional[float] = None,
        weather_warning: Optional[bool] = None,
        weather_condition: Optional[str] = None,
        current_vehicle_speed: Optional[float] = None,
        start_time: Optional[datetime] = None,
        config: Optional[ETAConfig] = None,
    ) -> ETAResult:
        """
        Estimate condition-aware ETA and expected delay for a route candidate.

        Args:
            candidate: Selected RouteCandidate, OptimizedRouteCandidate, route dict, or segment list.
            route_risk: Optional pre-calculated RouteRiskResult (prevents duplicate risk assessment).
            weather_snapshot: Optional WeatherSnapshot instance.
            rainfall_mm: Optional 24h rainfall in mm.
            weather_warning: Optional weather warning flag.
            weather_condition: Optional condition string ('clear', 'moderate', 'heavy', 'extreme').
            current_vehicle_speed: Optional current vehicle speed in km/h for telemetry delay.
            start_time: Optional timezone-aware start datetime.
            config: Optional ETAConfig (falls back to get_eta_config()).

        Returns:
            ETAResult with full adjustment breakdown and explainability.
        """
        active_config = config or get_eta_config()

        # 1. Unpack OptimizedRouteCandidate if wrapped
        underlying_candidate = candidate
        if hasattr(candidate, "route") and hasattr(candidate, "route_risk"):
            underlying_candidate = candidate.route
            if route_risk is None:
                route_risk = candidate.route_risk

        # 2. Extract Route Identifier and Distance
        route_id = getattr(underlying_candidate, 'route_id', None)
        if route_id is None and isinstance(underlying_candidate, dict):
            route_id = underlying_candidate.get('route_id', 'route-1')
        elif route_id is None:
            route_id = 'route-1'

        total_distance = cls._extract_distance(underlying_candidate)

        # 3. Resolve Segments for Calculation
        segments = cls._resolve_segment_dicts(underlying_candidate)

        # Handle empty route
        if not segments and total_distance <= 0.0:
            return ETAResult(
                route_id=route_id,
                distance_km=0.0,
                base_eta_minutes=0.0,
                adjusted_eta_minutes=0.0,
                expected_delay_minutes=0.0,
                delay_severity="none",
                start_time=start_time,
                estimated_arrival_time=start_time,
                adjustments=[],
                top_factors=[],
                explanation="No navigable route segments provided for ETA estimation.",
            )

        # 4. Canonical Single-Path Route Risk Resolution
        if route_risk is None:
            if hasattr(underlying_candidate, "route_risk") and underlying_candidate.route_risk:
                route_risk = underlying_candidate.route_risk
            else:
                route_risk = RouteRiskEngine.assess_route(underlying_candidate)

        # Enrich segment dicts with Canonical RouteRisk scores if available
        if route_risk and route_risk.segments:
            cls._enrich_segments_with_risk(segments, route_risk.segments)

        # 5. Base Travel Time
        # Prefer existing base_eta_minutes if present and positive
        existing_base_eta = getattr(underlying_candidate, 'base_eta_minutes', None)
        if existing_base_eta is None and isinstance(underlying_candidate, dict):
            existing_base_eta = underlying_candidate.get('base_eta_minutes')

        calc_base_time, seg_base_times = calculate_base_travel_time(segments, active_config)

        if existing_base_eta is not None and float(existing_base_eta) > 0:
            total_base_time = float(existing_base_eta)
            # Re-scale seg_base_times proportionally if needed
            if calc_base_time > 0 and abs(calc_base_time - total_base_time) > 0.01:
                ratio = total_base_time / calc_base_time
                seg_base_times = [t * ratio for t in seg_base_times]
        else:
            total_base_time = calc_base_time

        # Update total distance if not already set
        if total_distance <= 0.0:
            total_distance = sum(float(s.get('length_km', 0.0) or 0.0) for s in segments)

        # 6. Condition Adjustments
        all_adjustments: List[ETAFactorAdjustment] = []
        top_factors: List[str] = []

        # A. Segment Risk & Road Status Adjustments
        risk_delay, risk_adjs, risk_top_factors = calculate_segment_risk_adjustments(
            segments, seg_base_times, active_config
        )
        all_adjustments.extend(risk_adjs)
        top_factors.extend(risk_top_factors)

        # B. Weather Severity Adjustments
        rain, warning, cond = cls._extract_weather(
            weather_snapshot, rainfall_mm, weather_warning, weather_condition, segments
        )
        weather_delay, weather_adj, weather_top_factor = calculate_weather_adjustment(
            total_base_time, rain, warning, cond, active_config
        )
        if weather_adj:
            all_adjustments.append(weather_adj)
        if weather_top_factor:
            top_factors.append(weather_top_factor)

        # C. Real-Time Telemetry Adjustments
        telemetry_delay, telemetry_adj, telemetry_top_factor = calculate_telemetry_adjustment(
            total_base_time, total_distance, current_vehicle_speed, active_config
        )
        if telemetry_adj:
            all_adjustments.append(telemetry_adj)
        if telemetry_top_factor:
            top_factors.append(telemetry_top_factor)

        # 7. Final ETA and Delay Calculations
        total_adjusted_time = total_base_time + risk_delay + weather_delay + telemetry_delay
        expected_delay = max(0.0, total_adjusted_time - total_base_time)
        delay_severity = classify_delay_severity(expected_delay, active_config)

        # 8. Timezone-Aware Estimated Arrival Time
        estimated_arrival_time = None
        if start_time is not None:
            estimated_arrival_time = start_time + timedelta(minutes=total_adjusted_time)

        # 9. Explanation Generation
        explanation = cls._generate_explanation(
            total_base_time=total_base_time,
            adjusted_time=total_adjusted_time,
            expected_delay=expected_delay,
            delay_severity=delay_severity,
            adjustments=all_adjustments,
        )

        return ETAResult(
            route_id=route_id,
            distance_km=total_distance,
            base_eta_minutes=total_base_time,
            adjusted_eta_minutes=total_adjusted_time,
            expected_delay_minutes=expected_delay,
            delay_severity=delay_severity,
            start_time=start_time,
            estimated_arrival_time=estimated_arrival_time,
            adjustments=all_adjustments,
            top_factors=top_factors,
            explanation=explanation,
        )

    @classmethod
    def _extract_distance(cls, candidate: Any) -> float:
        dist = getattr(candidate, 'distance_km', None)
        if dist is not None:
            return float(dist)
        if isinstance(candidate, dict):
            return float(candidate.get('distance_km', 0.0) or 0.0)
        return 0.0

    @classmethod
    def _resolve_segment_dicts(cls, candidate: Any) -> List[Dict[str, Any]]:
        """
        Normalize various candidate segment representations into dictionaries.
        """
        if candidate is None:
            return []

        # 1. candidate.segments attribute
        if hasattr(candidate, "segments") and isinstance(candidate.segments, list):
            res = []
            for s in candidate.segments:
                if isinstance(s, dict):
                    res.append(dict(s))
                elif hasattr(s, "to_dict"):
                    res.append(s.to_dict())
                else:
                    res.append(cls._infra_to_dict(s))
            return res

        # 2. Dictionary with segments key
        if isinstance(candidate, dict) and 'segments' in candidate:
            return [dict(s) for s in candidate['segments']]

        # 3. Direct sequence of items
        if isinstance(candidate, (list, tuple)):
            res = []
            for item in candidate:
                if isinstance(item, dict):
                    res.append(dict(item))
                elif hasattr(item, "to_dict"):
                    res.append(item.to_dict())
                else:
                    res.append(cls._infra_to_dict(item))
            return res

        return []

    @classmethod
    def _infra_to_dict(cls, infra: Any) -> Dict[str, Any]:
        """Convert an Infrastructure model instance or object to a dict."""
        return {
            'id': getattr(infra, 'id', None),
            'name': getattr(infra, 'name', 'Road Segment'),
            'length_km': getattr(infra, 'length_km', 0.0),
            'road_classification': getattr(infra, 'road_classification', 'national_highway'),
            'base_speed_kmh': getattr(infra, 'base_speed_kmh', 45.0),
            'risk_score': getattr(infra, 'risk_score', 0.0),
            'risk_level': getattr(infra, 'risk_level', 'low'),
            'status': getattr(infra, 'status', 'accessible'),
            'condition': getattr(infra, 'condition', 'good'),
        }

    @classmethod
    def _enrich_segments_with_risk(
        cls,
        segments: List[Dict[str, Any]],
        risk_segments: List[RouteSegmentRisk],
    ) -> None:
        """
        Enrich segment dicts with canonical risk scores from RouteRiskResult.
        """
        if len(segments) == len(risk_segments):
            for seg, r_seg in zip(segments, risk_segments):
                if 'risk_score' not in seg or seg['risk_score'] == 0.0:
                    seg['risk_score'] = r_seg.risk_score
                if 'risk_level' not in seg or seg['risk_level'] == 'low':
                    seg['risk_level'] = r_seg.risk_level
                if not seg.get('name') and r_seg.name:
                    seg['name'] = r_seg.name
                if not seg.get('length_km') and r_seg.length_km:
                    seg['length_km'] = r_seg.length_km

    @classmethod
    def _extract_weather(
        cls,
        snapshot: Optional[Any],
        rain_mm: Optional[float],
        warning: Optional[bool],
        condition: Optional[str],
        segments: List[Dict[str, Any]],
    ) -> Tuple[Optional[float], Optional[bool], Optional[str]]:
        """
        Extract rainfall, warning, and condition from available inputs or snapshots.
        Does NOT make external HTTP requests.
        """
        # If explicitly passed values exist, use them
        if rain_mm is not None or warning is not None or condition is not None:
            return rain_mm, warning, condition

        # From weather_snapshot object
        if snapshot is not None:
            r = getattr(snapshot, 'rainfall_mm', None)
            w = getattr(snapshot, 'weather_warning', None)
            c = getattr(snapshot, 'condition', None)
            if isinstance(snapshot, dict):
                r = snapshot.get('rainfall_mm', r)
                w = snapshot.get('weather_warning', w)
                c = snapshot.get('condition', c)
            return r, w, str(c) if c else None

        # Check if segment models have district latest_weather
        for seg in segments:
            district = seg.get('district')
            if district and hasattr(district, 'latest_weather') and district.latest_weather:
                lw = district.latest_weather
                return lw.rainfall_mm, lw.weather_warning, lw.condition

        return None, None, None

    @classmethod
    def _generate_explanation(
        cls,
        total_base_time: float,
        adjusted_time: float,
        expected_delay: float,
        delay_severity: str,
        adjustments: List[ETAFactorAdjustment],
    ) -> str:
        """
        Produce a concise, human-readable summary explanation for the ETA estimation.
        """
        base_str = f"Base travel time is {round(total_base_time, 1)} minutes."

        if expected_delay <= 0.01:
            return f"{base_str} Route conditions are optimal with no anticipated delays."

        delay_str = f"Estimated arrival requires {round(adjusted_time, 1)} minutes (+{round(expected_delay, 1)} min delay, {delay_severity.upper()} severity)."

        factor_descriptions = [adj.description for adj in adjustments if adj.description]
        if factor_descriptions:
            factors_str = " Key factors: " + "; ".join(factor_descriptions) + "."
            return f"{base_str} {delay_str}{factors_str}"

        return f"{base_str} {delay_str}"
