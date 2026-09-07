"""
Celery tasks for routes and dynamic weather synchronization.
"""
import logging
from celery import shared_task
from apps.routes.models import District
from apps.routes.services.weather.service import WeatherService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_weather_task(self, district_id=None):
    """
    Scheduled background task to synchronize weather data.
    If district_id is provided, synchronizes only that district;
    otherwise synchronizes all districts with per-district failure isolation.
    """
    logger.info("Starting background weather sync task (district_id=%s)", district_id)
    try:
        if district_id:
            district = District.objects.get(id=district_id)
            snapshot = WeatherService.sync_district(district)
            return {
                'status': 'success',
                'district_id': district.id,
                'snapshot_id': snapshot.id,
                'rainfall_mm': snapshot.rainfall_mm,
                'condition': snapshot.condition,
            }
        else:
            result = WeatherService.sync_all_districts()
            return {
                'status': 'completed',
                'total': result['total'],
                'successful_count': result['successful_count'],
                'failed_count': result['failed_count'],
            }
    except Exception as exc:
        logger.error("Weather sync task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)

