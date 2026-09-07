"""
Base interface and dataclasses for Weather Providers.

WeatherProvider decouples the application layer (models, services, tasks)
from external APIs (Open-Meteo, IMD, ECMWF, or Mock providers).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class WeatherData:
    """
    Provider-agnostic normalized weather observation.
    """
    rainfall_mm: float
    condition: str
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    weather_warning: bool = False
    warning_details: str = ""
    recorded_at: Optional[datetime] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


class WeatherProvider(ABC):
    """
    Abstract interface that all weather data providers must implement.
    """

    @abstractmethod
    def fetch_weather(self, lat: float, lng: float) -> WeatherData:
        """
        Fetch real-time and 24-hour historical rainfall data for a geographic coordinate.

        Args:
            lat: WGS84 Latitude (-90.0 to 90.0)
            lng: WGS84 Longitude (-180.0 to 180.0)

        Returns:
            WeatherData dataclass populated with normalized fields.

        Raises:
            WeatherAPIError: On non-200 or upstream server failure.
            WeatherTimeoutError: On network connection timeout.
            WeatherValidationError: On invalid or malformed response structure.
        """
        pass

