"""
Condition Adjustment and Travel Time Calculation Functions.
"""
from typing import Any, Dict, List, Optional, Tuple
from apps.intelligence.services.eta.config import ETAConfig
from apps.intelligence.services.eta.result import ETAFactorAdjustment


def calculate_base_travel_time(
    segments: List[Dict[str, Any]],
    config: ETAConfig,
) -> Tuple[float, List[float]]:
    """
    Calculate base travel time in minutes per segment and in total.
    """
    total_base_time = 0.0
    seg_base_times: List[float] = []

    for seg in segments:
        length_km = float(seg.get('length_km', 0.0) or 0.0)
        road_class = (
            seg.get('road_classification')
            or seg.get('road_type')
            or 'national_highway'
        )
        base_speed = float(
            seg.get('base_speed_kmh')
            or config.road_class_speeds.get(road_class, config.default_speed_kmh)
        )
        if base_speed <= 0.0:
            base_speed = config.default_speed_kmh

        seg_base_time = (length_km / base_speed) * 60.0 if length_km > 0 else 0.0
        total_base_time += seg_base_time
        seg_base_times.append(seg_base_time)

    return total_base_time, seg_base_times


def calculate_segment_risk_adjustments(
    segments: List[Dict[str, Any]],
    seg_base_times: List[float],
    config: ETAConfig,
) -> Tuple[float, List[ETAFactorAdjustment], List[str]]:
    """
    Calculate deterministic delay penalties for hazardous or blocked segments.
    """
    total_risk_delay = 0.0
    adjustments: List[ETAFactorAdjustment] = []
    top_factors: List[str] = []

    for idx, seg in enumerate(segments):
        risk_score = float(seg.get('risk_score', 0.0) or 0.0)
        status = str(seg.get('status', 'accessible')).lower()
        condition = str(seg.get('condition', '')).lower()
        name = seg.get('name', f"Segment {idx + 1}")
        seg_base_time = seg_base_times[idx] if idx < len(seg_base_times) else 0.0

        # Blocked segment penalty
        if status == 'blocked':
            delay = config.blocked_segment_delay_minutes
            total_risk_delay += delay
            adj = ETAFactorAdjustment(
                category='blocked',
                name=f"Road blockage on {name}",
                delay_minutes=delay,
                multiplier=1.0,
                description=f"Road blockage on {name} (+{round(delay, 1)} mins)",
            )
            adjustments.append(adj)
            top_factors.append(f"Road blockage on {name} (+{round(delay, 1)} mins)")
            continue

        # High Risk segment penalty
        is_high_risk = (
            risk_score >= config.risk_threshold_high
            or status == 'risky'
            or condition == 'damaged'
        )

        if is_high_risk:
            # Scaled multiplier clamped between base_high_risk_multiplier and max_high_risk_multiplier
            if config.risk_threshold_high < 100.0:
                normalized_excess = max(0.0, min(1.0, (risk_score - config.risk_threshold_high) / (100.0 - config.risk_threshold_high)))
            else:
                normalized_excess = 0.0
            
            multiplier_span = config.max_high_risk_multiplier - config.base_high_risk_multiplier
            multiplier = min(
                config.max_high_risk_multiplier,
                max(config.base_high_risk_multiplier, config.base_high_risk_multiplier + (normalized_excess * multiplier_span))
            )
            seg_delay = seg_base_time * (multiplier - 1.0)
            total_risk_delay += seg_delay

            adj = ETAFactorAdjustment(
                category='segment_risk',
                name=f"Hazardous segment ({name})",
                delay_minutes=seg_delay,
                multiplier=multiplier,
                description=f"Hazardous segment ({name}) slow speed (+{round(seg_delay, 1)} mins)",
            )
            adjustments.append(adj)
            if seg_delay >= 0.5:
                top_factors.append(f"Hazardous segment ({name}) slow speed (+{round(seg_delay, 1)} mins)")

        # Medium Risk segment penalty
        elif risk_score >= config.risk_threshold_medium:
            multiplier = config.medium_risk_multiplier
            seg_delay = seg_base_time * (multiplier - 1.0)
            total_risk_delay += seg_delay

            adj = ETAFactorAdjustment(
                category='segment_risk',
                name=f"Moderate terrain risk ({name})",
                delay_minutes=seg_delay,
                multiplier=multiplier,
                description=f"Moderate terrain risk ({name}) (+{round(seg_delay, 1)} mins)",
            )
            adjustments.append(adj)
            if seg_delay >= 0.5:
                top_factors.append(f"Moderate terrain risk ({name}) (+{round(seg_delay, 1)} mins)")

    return total_risk_delay, adjustments, top_factors


def calculate_weather_adjustment(
    total_base_time: float,
    rainfall_mm: Optional[float],
    weather_warning: Optional[bool],
    weather_condition: Optional[str],
    config: ETAConfig,
) -> Tuple[float, Optional[ETAFactorAdjustment], Optional[str]]:
    """
    Calculate corridor weather delay from persisted rainfall, warning, or condition data.
    """
    if total_base_time <= 0.0:
        return 0.0, None, None

    # Missing dynamic weather data check
    if rainfall_mm is None and weather_warning is None and weather_condition is None:
        return 0.0, None, None

    rain = float(rainfall_mm or 0.0)
    cond = str(weather_condition or '').lower()
    warning = bool(weather_warning)

    weather_delay = 0.0
    adjustment: Optional[ETAFactorAdjustment] = None
    top_factor: Optional[str] = None

    if rain >= config.rainfall_threshold_heavy_mm or cond in ('heavy', 'extreme', 'severe'):
        weather_delay = total_base_time * config.rainfall_heavy_delay_factor
        adjustment = ETAFactorAdjustment(
            category='weather_severity',
            name='Heavy Rainfall',
            delay_minutes=weather_delay,
            multiplier=1.0 + config.rainfall_heavy_delay_factor,
            description=f"Heavy rainfall delay ({rain}mm, +{round(weather_delay, 1)} mins)",
        )
        top_factor = f"Heavy rainfall delay ({rain}mm, +{round(weather_delay, 1)} mins)"
    elif rain >= config.rainfall_threshold_moderate_mm or cond == 'moderate':
        weather_delay = total_base_time * config.rainfall_moderate_delay_factor
        adjustment = ETAFactorAdjustment(
            category='weather_severity',
            name='Moderate Rain',
            delay_minutes=weather_delay,
            multiplier=1.0 + config.rainfall_moderate_delay_factor,
            description=f"Moderate rain speed reduction (+{round(weather_delay, 1)} mins)",
        )
        top_factor = f"Moderate rain speed reduction (+{round(weather_delay, 1)} mins)"
    elif warning:
        weather_delay = total_base_time * config.weather_warning_delay_factor
        adjustment = ETAFactorAdjustment(
            category='weather_severity',
            name='Active IMD Advisory',
            delay_minutes=weather_delay,
            multiplier=1.0 + config.weather_warning_delay_factor,
            description=f"Active IMD advisory (+{round(weather_delay, 1)} mins)",
        )
        top_factor = f"Active IMD advisory (+{round(weather_delay, 1)} mins)"

    return weather_delay, adjustment, top_factor


def calculate_telemetry_adjustment(
    total_base_time: float,
    total_distance_km: float,
    current_vehicle_speed: Optional[float],
    config: ETAConfig,
) -> Tuple[float, Optional[ETAFactorAdjustment], Optional[str]]:
    """
    Calculate telemetry deficit delay when vehicle telemetry is provided.
    """
    if (
        current_vehicle_speed is None
        or current_vehicle_speed <= 0.0
        or total_base_time <= 0.0
        or total_distance_km <= 0.0
    ):
        return 0.0, None, None

    avg_base_speed = total_distance_km / (total_base_time / 60.0)
    if current_vehicle_speed < (avg_base_speed * config.telemetry_speed_deficit_ratio):
        telemetry_delay = total_base_time * config.telemetry_delay_factor
        adj = ETAFactorAdjustment(
            category='telemetry',
            name='Real-Time Traffic Slowdown',
            delay_minutes=telemetry_delay,
            multiplier=1.0 + config.telemetry_delay_factor,
            description=(
                f"Real-time vehicle slow moving traffic "
                f"({round(current_vehicle_speed, 1)} km/h, +{round(telemetry_delay, 1)} mins)"
            ),
        )
        top = f"Real-time vehicle slow moving traffic ({round(current_vehicle_speed, 1)} km/h, +{round(telemetry_delay, 1)} mins)"
        return telemetry_delay, adj, top

    return 0.0, None, None


def classify_delay_severity(expected_delay: float, config: ETAConfig) -> str:
    """
    Categorize expected delay into severity bands.
    """
    if expected_delay >= config.delay_threshold_critical:
        return 'critical'
    if expected_delay >= config.delay_threshold_moderate:
        return 'moderate'
    if expected_delay >= config.delay_threshold_minor:
        return 'minor'
    return 'none'

