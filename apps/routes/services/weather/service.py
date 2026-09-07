"""
Weather Ingestion and Synchronization Service.

Coordinates weather providers, district geometric location resolution, data normalization,
and WeatherSnapshot persistence with per-district failure isolation.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction

from apps.routes.models import District, WeatherSnapshot
from .base import WeatherData, WeatherProvider
from .exceptions import WeatherProviderError
from .mock import MockWeatherProvider
from .open_meteo import OpenMeteoProvider

logger = logging.getLogger(__name__)


class WeatherService:
    """
    Service responsible for orchestrating external weather ingestion
    and persisting district WeatherSnapshots.
    """

    @classmethod
    def get_provider(cls, provider_name: Optional[str] = None) -> WeatherProvider:
        """
        Factory method returning the configured WeatherProvider instance.
        Defaults to OpenMeteoProvider (production path).
        """
        name = (provider_name or getattr(settings, 'WEATHER_PROVIDER', 'open_meteo')).lower()

        if name == 'open_meteo':
            return OpenMeteoProvider()
        elif name == 'mock':
            return MockWeatherProvider()
        else:
            logger.warning(
                "Unrecognized WEATHER_PROVIDER '%s'. Falling back to OpenMeteoProvider.", name
            )
            return OpenMeteoProvider()

    @classmethod
    def resolve_district_coordinates(cls, district: District) -> Tuple[float, float]:
        """
        Derives a representative point (lat, lng) guaranteed to lie in or on the district
        geometry (point-on-surface) in WGS84 coordinate space.
        """
        return district.get_representative_point()

    @classmethod
    def sync_district(
        cls,
        district: District,
        provider: Optional[WeatherProvider] = None,
        dry_run: bool = False,
    ) -> WeatherSnapshot:
        """
        Synchronize weather for a single district.

        Fetches real weather, normalizes data, and persists a WeatherSnapshot.
        If dry_run is True, returns an unsaved WeatherSnapshot instance.
        """
        active_provider = provider or cls.get_provider()
        lat, lng = cls.resolve_district_coordinates(district)

        logger.info(
            "Synchronizing weather for district '%s' (id=%s) at coordinates (%s, %s) using %s",
            district.name, district.id, lat, lng, active_provider.__class__.__name__
        )

        weather_data: WeatherData = active_provider.fetch_weather(lat, lng)

        snapshot = WeatherSnapshot(
            district=district,
            rainfall_mm=weather_data.rainfall_mm,
            condition=weather_data.condition,
            temperature_c=weather_data.temperature_c,
            humidity_pct=weather_data.humidity_pct,
            wind_speed_kmh=weather_data.wind_speed_kmh,
            weather_warning=weather_data.weather_warning,
            warning_details=weather_data.warning_details,
            raw_payload=weather_data.raw_payload,
            recorded_at=weather_data.recorded_at,
        )

        if not dry_run:
            snapshot.save()
            logger.info(
                "Persisted WeatherSnapshot id=%s for district '%s': %s (%smm rain) at %s",
                snapshot.id, district.name, snapshot.condition, snapshot.rainfall_mm, snapshot.recorded_at
            )

        return snapshot

    @classmethod
    def sync_all_districts(
        cls,
        districts: Optional[List[District]] = None,
        provider: Optional[WeatherProvider] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Synchronize weather across all districts with isolated error boundaries.

        If district A fails, its previous snapshot is preserved, the error is logged,
        and subsequent districts continue to be processed without aborting.
        """
        target_districts = districts if districts is not None else list(District.objects.all())
        active_provider = provider or cls.get_provider()

        successful = []
        failed = []

        for district in target_districts:
            try:
                snapshot = cls.sync_district(district, provider=active_provider, dry_run=dry_run)
                successful.append({
                    'district_id': district.id,
                    'district_name': district.name,
                    'snapshot': snapshot,
                    'rainfall_mm': snapshot.rainfall_mm,
                    'condition': snapshot.condition,
                    'recorded_at': snapshot.recorded_at,
                })
            except Exception as e:
                logger.error(
                    "Failed to synchronize weather for district '%s' (id=%s): %s",
                    district.name, district.id, e, exc_info=True
                )
                last_snapshot = district.latest_weather
                failed.append({
                    'district_id': district.id,
                    'district_name': district.name,
                    'error': str(e),
                    'last_snapshot_recorded_at': (
                        last_snapshot.recorded_at.isoformat() if last_snapshot else None
                    ),
                })

        return {
            'total': len(target_districts),
            'successful_count': len(successful),
            'failed_count': len(failed),
            'successful': successful,
            'failed': failed,
            'dry_run': dry_run,
        }

