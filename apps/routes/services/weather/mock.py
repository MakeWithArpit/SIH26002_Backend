"""
Mock Weather Provider for hermetic testing and offline development.

Ensures the automated test suite and offline local environments never depend
on external network connectivity or public API rate limits.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from django.utils import timezone

from .base import WeatherData, WeatherProvider
from apps.routes.models import WeatherCondition


class MockWeatherProvider(WeatherProvider):
    """
    Hermetic test provider returning deterministic weather data.
    """

    def __init__(
        self,
        rainfall_mm: float = 5.0,
        condition: str = WeatherCondition.CLEAR,
        temperature_c: float = 24.0,
        humidity_pct: float = 75.0,
        wind_speed_kmh: float = 12.0,
        weather_warning: bool = False,
        warning_details: str = "",
        raise_error: Optional[Exception] = None,
    ):
        self.rainfall_mm = rainfall_mm
        self.condition = condition
        self.temperature_c = temperature_c
        self.humidity_pct = humidity_pct
        self.wind_speed_kmh = wind_speed_kmh
        self.weather_warning = weather_warning
        self.warning_details = warning_details
        self.raise_error = raise_error

    def fetch_weather(self, lat: float, lng: float) -> WeatherData:
        if self.raise_error is not None:
            raise self.raise_error

        now = timezone.now()
        return WeatherData(
            rainfall_mm=self.rainfall_mm,
            condition=self.condition,
            temperature_c=self.temperature_c,
            humidity_pct=self.humidity_pct,
            wind_speed_kmh=self.wind_speed_kmh,
            weather_warning=self.weather_warning,
            warning_details=self.warning_details,
            recorded_at=now,
            raw_payload={
                "mock": True,
                "lat": lat,
                "lng": lng,
                "rainfall_mm": self.rainfall_mm,
                "condition": self.condition,
                "recorded_at": now.isoformat(),
            },
        )

