"""
WMO (World Meteorological Organization) Weather Interpretation Code Mapping.

Deterministic classification of standard WMO weather codes (0-99) into the 4 target
conditions supported by the backend:
- clear: Code 0-3 (clear, mainly clear, partly cloudy, overcast)
- moderate: Code 45-63, 66, 71-73, 77, 80-81, 85 (fog, light/moderate rain, drizzle, light snow/showers)
- heavy: Code 65, 67, 75, 82, 86, 95 (heavy rain, heavy freezing rain, heavy snow, violent showers, thunderstorm)
- extreme: Code 96, 99 (severe thunderstorms with hail / extreme convective storms)

IMPORTANT: Per SIH-26 specification, WMO weather codes describe physical atmospheric
phenomena and are NEVER classified as official government weather warnings. Official
warnings are handled separately from authoritative warning feeds.
"""
from typing import Dict
from apps.routes.models import WeatherCondition

# Explicit deterministic WMO code mapping table
WMO_CODE_MAP: Dict[int, str] = {
    # Clear & Cloudiness
    0: WeatherCondition.CLEAR,       # Clear sky
    1: WeatherCondition.CLEAR,       # Mainly clear
    2: WeatherCondition.CLEAR,       # Partly cloudy
    3: WeatherCondition.CLEAR,       # Overcast

    # Fog
    45: WeatherCondition.MODERATE,   # Fog
    48: WeatherCondition.MODERATE,   # Depositing rime fog

    # Drizzle
    51: WeatherCondition.MODERATE,   # Drizzle: Light
    53: WeatherCondition.MODERATE,   # Drizzle: Moderate
    55: WeatherCondition.MODERATE,   # Drizzle: Dense intensity
    56: WeatherCondition.MODERATE,   # Freezing Drizzle: Light
    57: WeatherCondition.MODERATE,   # Freezing Drizzle: Dense intensity

    # Rain
    61: WeatherCondition.MODERATE,   # Rain: Slight
    63: WeatherCondition.MODERATE,   # Rain: Moderate
    65: WeatherCondition.HEAVY,      # Rain: Heavy intensity
    66: WeatherCondition.MODERATE,   # Freezing Rain: Light
    67: WeatherCondition.HEAVY,      # Freezing Rain: Heavy intensity

    # Snow
    71: WeatherCondition.MODERATE,   # Snow fall: Slight
    73: WeatherCondition.MODERATE,   # Snow fall: Moderate
    75: WeatherCondition.HEAVY,      # Snow fall: Heavy intensity
    77: WeatherCondition.MODERATE,   # Snow grains

    # Showers
    80: WeatherCondition.MODERATE,   # Rain showers: Slight
    81: WeatherCondition.MODERATE,   # Rain showers: Moderate
    82: WeatherCondition.HEAVY,      # Rain showers: Violent
    85: WeatherCondition.MODERATE,   # Snow showers: Slight
    86: WeatherCondition.HEAVY,      # Snow showers: Heavy

    # Thunderstorms
    95: WeatherCondition.HEAVY,      # Thunderstorm: Slight or moderate
    96: WeatherCondition.EXTREME,    # Thunderstorm with slight hail
    99: WeatherCondition.EXTREME,    # Thunderstorm with heavy hail
}


def wmo_code_to_condition(code: int) -> str:
    """
    Map an integer WMO weather code to one of:
    'clear', 'moderate', 'heavy', 'extreme'.

    If an unexpected or unmapped code is encountered, maps conservatively
    based on the severity decade.
    """
    if code in WMO_CODE_MAP:
        return WMO_CODE_MAP[code]

    # Deterministic fallback for unmapped edge-case codes
    if code >= 95:
        return WeatherCondition.EXTREME if code in (96, 99) else WeatherCondition.HEAVY
    elif code >= 80:
        return WeatherCondition.HEAVY if code in (82, 86) else WeatherCondition.MODERATE
    elif code >= 40:
        return WeatherCondition.MODERATE
    return WeatherCondition.CLEAR

