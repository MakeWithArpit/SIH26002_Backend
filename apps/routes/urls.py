from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import DistrictViewSet, InfrastructureViewSet, CalculateRouteView, SimulatePipelineView
from .views_alerts import AlertsView, AlertGenerateView, AlertResolveView, AlertSummaryView
from .views_accessibility import DistrictAccessibilityView, AccessibilityRefreshView
from .views_weather import (
    trigger_weather_sync,
    trigger_weather_risk_pipeline,
    get_latest_weather,
    get_district_weather_history,
)

router = DefaultRouter()
router.register(r'districts', DistrictViewSet, basename='district')
router.register(r'infrastructure', InfrastructureViewSet, basename='infrastructure')

urlpatterns = [
    path('calculate/', CalculateRouteView.as_view(), name='calculate-route'),
    path('simulate-pipeline/', SimulatePipelineView.as_view(), name='simulate-pipeline'),
    
    # Phase 8: Alert Endpoints
    path('alerts/', AlertsView.as_view(), name='alerts'),
    path('alerts/generate/', AlertGenerateView.as_view(), name='alert-generate'),
    path('alerts/summary/', AlertSummaryView.as_view(), name='alert-summary'),
    path('alerts/<str:alert_id>/resolve/', AlertResolveView.as_view(), name='alert-resolve'),
    
    # Phase 10: Accessibility Intelligence Endpoints
    path('districts/<int:district_id>/accessibility/', DistrictAccessibilityView.as_view(), name='district-accessibility'),
    path('districts/accessibility/refresh/', AccessibilityRefreshView.as_view(), name='accessibility-refresh'),
    
    # Phase 6: Weather Intelligence Endpoints
    path('weather/sync/', trigger_weather_sync, name='trigger-weather-sync'),
    path('weather/sync-and-update-risk/', trigger_weather_risk_pipeline, name='trigger-weather-risk-pipeline'),
    path('weather/latest/', get_latest_weather, name='get-latest-weather'),
    path('weather/districts/<int:district_id>/history/', get_district_weather_history, name='district-weather-history'),
] + router.urls
