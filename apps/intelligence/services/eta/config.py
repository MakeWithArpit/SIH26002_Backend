"""
Centralized Configuration for ETA Estimation Engine.

Defines road speeds, risk penalty coefficients, dynamic weather delays,
and delay classification thresholds.
"""
from dataclasses import dataclass, field
from typing import Dict
from django.conf import settings

# Default Road Classification Speeds (km/h)
DEFAULT_ROAD_CLASS_SPEEDS: Dict[str, float] = {
    'national_highway': 50.0,
    'state_highway': 40.0,
    'major_district_road': 30.0,
    'rural_road': 25.0,
    'bridge': 30.0,
    'tunnel': 40.0,
}

DEFAULT_SPEED_KMH = 45.0

# Canonical Phase 7 Risk Thresholds
DEFAULT_RISK_THRESHOLD_MEDIUM = 40.0
DEFAULT_RISK_THRESHOLD_HIGH = 70.0

# Risk Multipliers / Delay
DEFAULT_MEDIUM_RISK_MULTIPLIER = 1.15
DEFAULT_BASE_HIGH_RISK_MULTIPLIER = 1.40
DEFAULT_MAX_HIGH_RISK_MULTIPLIER = 1.75
DEFAULT_BLOCKED_SEGMENT_DELAY_MIN = 120.0

# Dynamic Weather Thresholds & Delay Factors
DEFAULT_RAINFALL_THRESHOLD_MODERATE_MM = 20.0
DEFAULT_RAINFALL_THRESHOLD_HEAVY_MM = 50.0
DEFAULT_RAINFALL_MODERATE_DELAY_FACTOR = 0.12
DEFAULT_RAINFALL_HEAVY_DELAY_FACTOR = 0.25
DEFAULT_WEATHER_WARNING_DELAY_FACTOR = 0.10

# Real-Time Telemetry Deficit
DEFAULT_TELEMETRY_SPEED_DEFICIT_RATIO = 0.60
DEFAULT_TELEMETRY_DELAY_FACTOR = 0.15

# Delay Severity Thresholds (minutes)
DEFAULT_DELAY_THRESHOLD_MINOR = 5.0
DEFAULT_DELAY_THRESHOLD_MODERATE = 20.0
DEFAULT_DELAY_THRESHOLD_CRITICAL = 45.0


@dataclass(frozen=True)
class ETAConfig:
    """
    Typed, immutable configuration for ETA and delay calculations.
    """
    road_class_speeds: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_ROAD_CLASS_SPEEDS))
    default_speed_kmh: float = DEFAULT_SPEED_KMH

    risk_threshold_medium: float = DEFAULT_RISK_THRESHOLD_MEDIUM
    risk_threshold_high: float = DEFAULT_RISK_THRESHOLD_HIGH

    medium_risk_multiplier: float = DEFAULT_MEDIUM_RISK_MULTIPLIER
    base_high_risk_multiplier: float = DEFAULT_BASE_HIGH_RISK_MULTIPLIER
    max_high_risk_multiplier: float = DEFAULT_MAX_HIGH_RISK_MULTIPLIER
    blocked_segment_delay_minutes: float = DEFAULT_BLOCKED_SEGMENT_DELAY_MIN

    rainfall_threshold_moderate_mm: float = DEFAULT_RAINFALL_THRESHOLD_MODERATE_MM
    rainfall_threshold_heavy_mm: float = DEFAULT_RAINFALL_THRESHOLD_HEAVY_MM
    rainfall_moderate_delay_factor: float = DEFAULT_RAINFALL_MODERATE_DELAY_FACTOR
    rainfall_heavy_delay_factor: float = DEFAULT_RAINFALL_HEAVY_DELAY_FACTOR
    weather_warning_delay_factor: float = DEFAULT_WEATHER_WARNING_DELAY_FACTOR

    telemetry_speed_deficit_ratio: float = DEFAULT_TELEMETRY_SPEED_DEFICIT_RATIO
    telemetry_delay_factor: float = DEFAULT_TELEMETRY_DELAY_FACTOR

    delay_threshold_minor: float = DEFAULT_DELAY_THRESHOLD_MINOR
    delay_threshold_moderate: float = DEFAULT_DELAY_THRESHOLD_MODERATE
    delay_threshold_critical: float = DEFAULT_DELAY_THRESHOLD_CRITICAL


def get_eta_config() -> ETAConfig:
    """
    Instantiate ETAConfig from Django settings, falling back to defaults.
    """
    eta_settings = getattr(settings, 'ETA_CONFIG', {})

    speeds = dict(DEFAULT_ROAD_CLASS_SPEEDS)
    if 'road_class_speeds' in eta_settings:
        speeds.update(eta_settings['road_class_speeds'])

    return ETAConfig(
        road_class_speeds=speeds,
        default_speed_kmh=float(eta_settings.get('default_speed_kmh', DEFAULT_SPEED_KMH)),
        risk_threshold_medium=float(eta_settings.get('risk_threshold_medium', DEFAULT_RISK_THRESHOLD_MEDIUM)),
        risk_threshold_high=float(eta_settings.get('risk_threshold_high', DEFAULT_RISK_THRESHOLD_HIGH)),
        medium_risk_multiplier=float(eta_settings.get('medium_risk_multiplier', DEFAULT_MEDIUM_RISK_MULTIPLIER)),
        base_high_risk_multiplier=float(eta_settings.get('base_high_risk_multiplier', DEFAULT_BASE_HIGH_RISK_MULTIPLIER)),
        max_high_risk_multiplier=float(eta_settings.get('max_high_risk_multiplier', DEFAULT_MAX_HIGH_RISK_MULTIPLIER)),
        blocked_segment_delay_minutes=float(eta_settings.get('blocked_segment_delay_minutes', DEFAULT_BLOCKED_SEGMENT_DELAY_MIN)),
        rainfall_threshold_moderate_mm=float(eta_settings.get('rainfall_threshold_moderate_mm', DEFAULT_RAINFALL_THRESHOLD_MODERATE_MM)),
        rainfall_threshold_heavy_mm=float(eta_settings.get('rainfall_threshold_heavy_mm', DEFAULT_RAINFALL_THRESHOLD_HEAVY_MM)),
        rainfall_moderate_delay_factor=float(eta_settings.get('rainfall_moderate_delay_factor', DEFAULT_RAINFALL_MODERATE_DELAY_FACTOR)),
        rainfall_heavy_delay_factor=float(eta_settings.get('rainfall_heavy_delay_factor', DEFAULT_RAINFALL_HEAVY_DELAY_FACTOR)),
        weather_warning_delay_factor=float(eta_settings.get('weather_warning_delay_factor', DEFAULT_WEATHER_WARNING_DELAY_FACTOR)),
        telemetry_speed_deficit_ratio=float(eta_settings.get('telemetry_speed_deficit_ratio', DEFAULT_TELEMETRY_SPEED_DEFICIT_RATIO)),
        telemetry_delay_factor=float(eta_settings.get('telemetry_delay_factor', DEFAULT_TELEMETRY_DELAY_FACTOR)),
        delay_threshold_minor=float(eta_settings.get('delay_threshold_minor', DEFAULT_DELAY_THRESHOLD_MINOR)),
        delay_threshold_moderate=float(eta_settings.get('delay_threshold_moderate', DEFAULT_DELAY_THRESHOLD_MODERATE)),
        delay_threshold_critical=float(eta_settings.get('delay_threshold_critical', DEFAULT_DELAY_THRESHOLD_CRITICAL)),
    )

