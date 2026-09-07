"""
Centralized Configuration for Infrastructure Risk Engine.
"""
from dataclasses import dataclass
from django.conf import settings

# Default Weight Constants
DEFAULT_LANDSLIDE_SUSCEPTIBILITY_HIGH = 30.0
DEFAULT_HISTORICAL_LANDSLIDE = 15.0
DEFAULT_FLOOD_HAZARD = 15.0
DEFAULT_HEAVY_RAINFALL = 25.0
DEFAULT_WEATHER_WARNING = 10.0

# Default Threshold Constants
DEFAULT_RAINFALL_MIN_THRESHOLD_MM = 20.0
DEFAULT_RAINFALL_MAX_THRESHOLD_MM = 50.0

# Default Level Classification Thresholds
# 0 - 39: LOW
# 40 - 69: MEDIUM
# 70 - 100: HIGH
DEFAULT_RISK_LEVEL_LOW_MAX = 39.0
DEFAULT_RISK_LEVEL_MEDIUM_MAX = 69.0


@dataclass(frozen=True)
class RiskConfig:
    """
    Typed, immutable configuration for risk calculations.
    """
    weight_landslide_susceptibility_high: float = DEFAULT_LANDSLIDE_SUSCEPTIBILITY_HIGH
    weight_historical_landslide: float = DEFAULT_HISTORICAL_LANDSLIDE
    weight_flood_hazard: float = DEFAULT_FLOOD_HAZARD
    weight_heavy_rainfall: float = DEFAULT_HEAVY_RAINFALL
    weight_weather_warning: float = DEFAULT_WEATHER_WARNING

    rainfall_min_threshold_mm: float = DEFAULT_RAINFALL_MIN_THRESHOLD_MM
    rainfall_max_threshold_mm: float = DEFAULT_RAINFALL_MAX_THRESHOLD_MM

    threshold_low_max: float = DEFAULT_RISK_LEVEL_LOW_MAX
    threshold_medium_max: float = DEFAULT_RISK_LEVEL_MEDIUM_MAX


def get_risk_config() -> RiskConfig:
    """
    Instantiate RiskConfig from Django settings, falling back to defaults.
    """
    return RiskConfig(
        weight_landslide_susceptibility_high=float(
            getattr(settings, 'RISK_WEIGHT_LANDSLIDE_SUSCEPTIBILITY_HIGH', DEFAULT_LANDSLIDE_SUSCEPTIBILITY_HIGH)
        ),
        weight_historical_landslide=float(
            getattr(settings, 'RISK_WEIGHT_HISTORICAL_LANDSLIDE', DEFAULT_HISTORICAL_LANDSLIDE)
        ),
        weight_flood_hazard=float(
            getattr(settings, 'RISK_WEIGHT_FLOOD_HAZARD', DEFAULT_FLOOD_HAZARD)
        ),
        weight_heavy_rainfall=float(
            getattr(settings, 'RISK_WEIGHT_HEAVY_RAINFALL', DEFAULT_HEAVY_RAINFALL)
        ),
        weight_weather_warning=float(
            getattr(settings, 'RISK_WEIGHT_WEATHER_WARNING', DEFAULT_WEATHER_WARNING)
        ),
        rainfall_min_threshold_mm=float(
            getattr(settings, 'RISK_RAINFALL_MIN_MM', DEFAULT_RAINFALL_MIN_THRESHOLD_MM)
        ),
        rainfall_max_threshold_mm=float(
            getattr(settings, 'RISK_RAINFALL_MAX_MM', DEFAULT_RAINFALL_MAX_THRESHOLD_MM)
        ),
        threshold_low_max=float(
            getattr(settings, 'RISK_THRESHOLD_LOW_MAX', DEFAULT_RISK_LEVEL_LOW_MAX)
        ),
        threshold_medium_max=float(
            getattr(settings, 'RISK_THRESHOLD_MEDIUM_MAX', DEFAULT_RISK_LEVEL_MEDIUM_MAX)
        ),
    )
