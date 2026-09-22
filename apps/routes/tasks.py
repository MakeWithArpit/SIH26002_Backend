"""
Celery tasks for routes and dynamic weather synchronization.
"""
import logging
from celery import shared_task
from django.db import transaction
from apps.routes.models import District, Infrastructure
from apps.routes.services.weather.service import WeatherService
from apps.routes.services.risk import RiskPredictionService

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


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def sync_weather_and_update_risk_task(self):
    """
    Phase 6 integrated task: Synchronize weather data and propagate to infrastructure risk scores.
    
    Flow:
    1. Sync weather for all districts
    2. For each district, update infrastructure risk scores using latest weather data
    3. Return summary of weather sync + risk updates
    """
    logger.info("Starting integrated weather sync + risk update task")
    
    try:
        weather_result = WeatherService.sync_all_districts()
        logger.info(
            "Weather sync completed: %s/%s districts successful",
            weather_result['successful_count'],
            weather_result['total']
        )
        
        updated_infra_count = 0
        high_risk_count = 0
        
        for success_record in weather_result['successful']:
            district_id = success_record['district_id']
            snapshot = success_record['snapshot']
            
            district = District.objects.get(id=district_id)
            infrastructure_segments = Infrastructure.objects.filter(district=district)
            
            logger.info(
                "Propagating weather data to %s infrastructure segments in district '%s'",
                infrastructure_segments.count(),
                district.name
            )
            
            for infra in infrastructure_segments:
                with transaction.atomic():
                    infra.recent_rainfall_mm = snapshot.rainfall_mm
                    infra.weather_warning = snapshot.weather_warning
                    
                    risk_result = RiskPredictionService.calculate_risk(infra)
                    
                    infra.risk_score = risk_result['risk_score']
                    infra.risk_level = risk_result['risk_level']
                    infra.disruption_probability = risk_result['disruption_probability']
                    infra.top_factors = risk_result['top_factors']
                    
                    infra.save()
                    
                    updated_infra_count += 1
                    if risk_result['risk_level'] == 'high':
                        high_risk_count += 1
        
        logger.info(
            "Risk update completed: %s infrastructure segments updated, %s high-risk segments",
            updated_infra_count,
            high_risk_count
        )
        
        return {
            'status': 'completed',
            'weather_sync': {
                'total_districts': weather_result['total'],
                'successful': weather_result['successful_count'],
                'failed': weather_result['failed_count'],
            },
            'risk_update': {
                'updated_segments': updated_infra_count,
                'high_risk_segments': high_risk_count,
            },
        }
        
    except Exception as exc:
        logger.error("Integrated weather+risk task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def update_infrastructure_risk_task(self, district_id=None):
    """
    Standalone task to recalculate risk scores for infrastructure segments.
    Can be triggered manually or after weather updates.
    """
    logger.info("Starting infrastructure risk update task (district_id=%s)", district_id)
    
    try:
        if district_id:
            infrastructure_qs = Infrastructure.objects.filter(district_id=district_id)
        else:
            infrastructure_qs = Infrastructure.objects.all()
        
        updated_count = 0
        high_risk_count = 0
        
        for infra in infrastructure_qs:
            risk_result = RiskPredictionService.calculate_risk(infra)
            
            infra.risk_score = risk_result['risk_score']
            infra.risk_level = risk_result['risk_level']
            infra.disruption_probability = risk_result['disruption_probability']
            infra.top_factors = risk_result['top_factors']
            infra.save()
            
            updated_count += 1
            if risk_result['risk_level'] == 'high':
                high_risk_count += 1
        
        logger.info(
            "Risk update completed: %s segments updated, %s high-risk",
            updated_count,
            high_risk_count
        )
        
        return {
            'status': 'success',
            'updated_count': updated_count,
            'high_risk_count': high_risk_count,
        }
        
    except Exception as exc:
        logger.error("Risk update task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)

