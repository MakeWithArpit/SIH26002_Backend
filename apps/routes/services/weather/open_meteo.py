"""
Open-Meteo External Weather Provider.

Implements the WeatherProvider interface by fetching real meteorological data
from the Open-Meteo forecast API (https://api.open-meteo.com/v1/forecast).
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import zoneinfo
import requests

from django.conf import settings
from django.utils import timezone as django_tz

from .base import WeatherData, WeatherProvider
from .exceptions import WeatherAPIError, WeatherTimeoutError, WeatherValidationError
from .wmo import wmo_code_to_condition

logger = logging.getLogger(__name__)


class OpenMeteoProvider(WeatherProvider):
    """
    Production weather provider querying the Open-Meteo REST API.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        recent_hours: Optional[int] = None,
    ):
        self.base_url = base_url or getattr(
            settings, 'OPEN_METEO_BASE_URL', 'https://api.open-meteo.com/v1/forecast'
        )
        self.timeout_seconds = timeout_seconds or float(
            getattr(settings, 'OPEN_METEO_TIMEOUT_SECONDS', 10.0)
        )
        self.recent_hours = recent_hours or int(
            getattr(settings, 'WEATHER_RECENT_RAINFALL_HOURS', 24)
        )

    def fetch_weather(self, lat: float, lng: float) -> WeatherData:
        """
        Query Open-Meteo for current conditions and past 24-hour rainfall.
        """
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
            raise WeatherValidationError(f"Coordinates out of bounds: lat={lat}, lng={lng}")

        params = {
            'latitude': round(lat, 4),
            'longitude': round(lng, 4),
            'current': 'temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m',
            'hourly': 'rain,precipitation,weather_code,temperature_2m,relative_humidity_2m,wind_speed_10m',
            'past_hours': self.recent_hours,
            'forecast_hours': 1,
            'timezone': 'auto',
        }

        try:
            logger.debug(
                "Fetching weather from Open-Meteo for lat=%s, lng=%s at %s",
                lat, lng, self.base_url
            )
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.Timeout as e:
            logger.error("Open-Meteo request timed out after %ss: %s", self.timeout_seconds, e)
            raise WeatherTimeoutError(
                f"Open-Meteo API timed out after {self.timeout_seconds}s for ({lat}, {lng})"
            ) from e
        except requests.exceptions.RequestException as e:
            logger.error("Open-Meteo network/connection failure: %s", e)
            raise WeatherAPIError(
                f"Open-Meteo connection error for ({lat}, {lng}): {str(e)}"
            ) from e

        if response.status_code != 200:
            logger.error(
                "Open-Meteo returned HTTP %s for (%s, %s): %s",
                response.status_code, lat, lng, response.text[:200]
            )
            raise WeatherAPIError(
                f"Open-Meteo returned HTTP {response.status_code}",
                status_code=response.status_code,
                response_body=response.text[:500],
            )

        try:
            payload = response.json()
        except Exception as e:
            raise WeatherValidationError(f"Invalid JSON in Open-Meteo response: {e}") from e

        return self.normalize_payload(payload, lat, lng)

    def normalize_payload(self, payload: Dict[str, Any], lat: float, lng: float) -> WeatherData:
        """
        Validate and normalize the raw Open-Meteo JSON payload into a WeatherData dataclass.
        """
        if not isinstance(payload, dict):
            raise WeatherValidationError("Open-Meteo response root must be a JSON object.")

        current = payload.get('current')
        if not isinstance(current, dict):
            raise WeatherValidationError("Missing or invalid 'current' object in Open-Meteo response.")

        hourly = payload.get('hourly')
        if not isinstance(hourly, dict):
            raise WeatherValidationError("Missing or invalid 'hourly' object in Open-Meteo response.")

        # Required fields in current
        for req_field in ('time', 'weather_code', 'temperature_2m', 'relative_humidity_2m', 'wind_speed_10m'):
            if req_field not in current:
                raise WeatherValidationError(f"Missing required field '{req_field}' in 'current' weather data.")

        # Required fields in hourly
        for req_hourly in ('time', 'rain'):
            if req_hourly not in hourly:
                raise WeatherValidationError(f"Missing required field '{req_hourly}' in 'hourly' weather data.")

        hourly_times = hourly.get('time')
        hourly_rains = hourly.get('rain')
        if not isinstance(hourly_times, list) or not isinstance(hourly_rains, list):
            raise WeatherValidationError("'hourly.time' and 'hourly.rain' must be lists.")

        if len(hourly_times) != len(hourly_rains):
            raise WeatherValidationError("Mismatch between length of 'hourly.time' and 'hourly.rain'.")

        # Resolve observation timestamp & timezone
        tz_name = payload.get('timezone', 'UTC')
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = zoneinfo.ZoneInfo('UTC')

        raw_time_str = current['time']
        try:
            naive_dt = datetime.fromisoformat(raw_time_str)
            recorded_at = naive_dt.replace(tzinfo=tz)
        except Exception as e:
            raise WeatherValidationError(f"Unable to parse 'current.time' ({raw_time_str}): {e}") from e

        # Calculate 24-hour rainfall sum strictly from previous hourly values
        rainfall_24h = self._calculate_24h_rainfall(
            hourly_times=hourly_times,
            hourly_rains=hourly_rains,
            current_time=recorded_at,
            tz=tz,
        )

        # Condition mapping via deterministic WMO table
        raw_wmo_code = current['weather_code']
        if not isinstance(raw_wmo_code, (int, float)):
            raise WeatherValidationError(f"Invalid weather_code '{raw_wmo_code}': must be numeric.")
        condition = wmo_code_to_condition(int(raw_wmo_code))

        # Temperature, humidity, wind speed
        try:
            temp_c = float(current['temperature_2m']) if current.get('temperature_2m') is not None else None
            humidity = float(current['relative_humidity_2m']) if current.get('relative_humidity_2m') is not None else None
            wind_kmh = float(current['wind_speed_10m']) if current.get('wind_speed_10m') is not None else None
        except (ValueError, TypeError) as e:
            raise WeatherValidationError(f"Error converting current weather metrics to float: {e}") from e

        return WeatherData(
            rainfall_mm=rainfall_24h,
            condition=condition,
            temperature_c=temp_c,
            humidity_pct=humidity,
            wind_speed_kmh=wind_kmh,
            weather_warning=False,  # Per PRD, WMO code is NEVER an official government warning
            warning_details="",
            recorded_at=recorded_at,
            raw_payload=payload,
        )

    def _calculate_24h_rainfall(
        self,
        hourly_times: List[str],
        hourly_rains: List[Any],
        current_time: datetime,
        tz: zoneinfo.ZoneInfo,
    ) -> float:
        """
        Sums previous 24 hourly rain values up to current_time.
        Handles missing/null values safely by treating them as 0.0.
        Validates that all values are valid non-negative numbers.
        """
        # Parse all hourly entries
        entries = []
        for t_str, r_val in zip(hourly_times, hourly_rains):
            try:
                dt = datetime.fromisoformat(t_str).replace(tzinfo=tz)
                entries.append((dt, r_val))
            except Exception:
                continue

        # Filter entries occurring on or before current_time
        past_entries = [r for dt, r in entries if dt <= current_time]

        # If past_entries is empty, fallback to taking the last available entries
        if not past_entries:
            past_entries = hourly_rains

        # Take up to the requested number of past hourly intervals (e.g. 24)
        window = past_entries[-self.recent_hours:]

        total_rain = 0.0
        for val in window:
            if val is None:
                # Null values in Open-Meteo indicate no rain recorded for that hour
                continue
            if not isinstance(val, (int, float)):
                raise WeatherValidationError(f"Invalid non-numeric rainfall value in hourly data: {val}")
            if val < 0.0:
                raise WeatherValidationError(f"Negative rainfall value encountered: {val}")
            total_rain += float(val)

        return round(total_rain, 2)

