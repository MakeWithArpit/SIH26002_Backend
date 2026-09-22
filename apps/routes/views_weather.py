"""
Weather synchronization API views for Phase 6.
"""
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.common.responses import standard_response
from apps.routes.models import District, WeatherSnapshot
from apps.routes.services.weather.service import WeatherService
from apps.routes.tasks import sync_weather_task, sync_weather_and_update_risk_task

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['Weather Intelligence'],
    summary="Trigger manual weather synchronization",
    description="Manually trigger weather data synchronization for all districts or a specific district. "
                "This endpoint queues an async Celery task and returns immediately.",
    parameters=[],
    request=None,
    responses={
        200: OpenApiResponse(description="Weather sync task queued successfully"),
        500: OpenApiResponse(description="Failed to queue weather sync task"),
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_weather_sync(request):
    """
    POST /api/v1/weather/sync/
    
    Manually trigger weather synchronization task (async via Celery).
    Returns task ID for tracking.
    """
    try:
        task = sync_weather_task.delay()
        return standard_response(
            data={
                'task_id': task.id,
                'status': 'queued',
                'message': 'Weather synchronization task queued successfully',
            },
            message="Weather sync task queued",
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logger.error("Failed to queue weather sync task: %s", e, exc_info=True)
        return standard_response(
            message="Failed to queue weather synchronization task",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Weather Intelligence'],
    summary="Trigger weather sync + risk update pipeline",
    description="Manually trigger the integrated weather synchronization and infrastructure risk recalculation pipeline. "
                "This is the Phase 6 end-to-end workflow: weather fetch → risk score propagation.",
    responses={
        200: OpenApiResponse(description="Integrated pipeline task queued successfully"),
        500: OpenApiResponse(description="Failed to queue pipeline task"),
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_weather_risk_pipeline(request):
    """
    POST /api/v1/weather/sync-and-update-risk/
    
    Trigger the Phase 6 integrated pipeline:
    1. Sync weather for all districts
    2. Propagate weather data to infrastructure risk scores
    """
    try:
        task = sync_weather_and_update_risk_task.delay()
        return standard_response(
            data={
                'task_id': task.id,
                'status': 'queued',
                'message': 'Weather sync + risk update pipeline queued successfully',
            },
            message="Integrated weather-risk pipeline task queued",
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logger.error("Failed to queue weather-risk pipeline task: %s", e, exc_info=True)
        return standard_response(
            message="Failed to queue integrated pipeline task",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Weather Intelligence'],
    summary="Get latest weather snapshots",
    description="Retrieve the most recent weather snapshot for each district in the system.",
    responses={
        200: OpenApiResponse(description="Latest weather snapshots retrieved successfully"),
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_latest_weather(request):
    """
    GET /api/v1/weather/latest/
    
    Returns the latest WeatherSnapshot for each district.
    """
    districts = District.objects.all()
    
    weather_data = []
    for district in districts:
        latest = district.latest_weather
        if latest:
            weather_data.append({
                'district_id': district.id,
                'district_name': district.name,
                'state': district.state,
                'rainfall_mm': latest.rainfall_mm,
                'condition': latest.condition,
                'temperature_c': latest.temperature_c,
                'humidity_pct': latest.humidity_pct,
                'wind_speed_kmh': latest.wind_speed_kmh,
                'weather_warning': latest.weather_warning,
                'warning_details': latest.warning_details,
                'recorded_at': latest.recorded_at,
            })
    
    return standard_response(
        data={
            'count': len(weather_data),
            'weather_snapshots': weather_data,
        },
        message="Latest weather snapshots retrieved successfully",
        status_code=status.HTTP_200_OK
    )


@extend_schema(
    tags=['Weather Intelligence'],
    summary="Get weather history for a district",
    description="Retrieve paginated weather snapshot history for a specific district.",
    responses={
        200: OpenApiResponse(description="Weather history retrieved successfully"),
        404: OpenApiResponse(description="District not found"),
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_district_weather_history(request, district_id):
    """
    GET /api/v1/weather/districts/{district_id}/history/
    
    Returns paginated weather snapshot history for a district.
    """
    try:
        district = District.objects.get(id=district_id)
    except District.DoesNotExist:
        return standard_response(
            message=f"District with ID {district_id} not found",
            success=False,
            status_code=status.HTTP_404_NOT_FOUND
        )
    
    limit = int(request.GET.get('limit', 10))
    offset = int(request.GET.get('offset', 0))
    
    snapshots = district.weather_snapshots.all()[offset:offset + limit]
    total_count = district.weather_snapshots.count()
    
    snapshot_data = []
    for snapshot in snapshots:
        snapshot_data.append({
            'id': snapshot.id,
            'rainfall_mm': snapshot.rainfall_mm,
            'condition': snapshot.condition,
            'temperature_c': snapshot.temperature_c,
            'humidity_pct': snapshot.humidity_pct,
            'wind_speed_kmh': snapshot.wind_speed_kmh,
            'weather_warning': snapshot.weather_warning,
            'warning_details': snapshot.warning_details,
            'recorded_at': snapshot.recorded_at,
            'created_at': snapshot.created_at,
        })
    
    return standard_response(
        data={
            'district_id': district.id,
            'district_name': district.name,
            'total_count': total_count,
            'limit': limit,
            'offset': offset,
            'snapshots': snapshot_data,
        },
        message="Weather history retrieved successfully",
        status_code=status.HTTP_200_OK
    )
