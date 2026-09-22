"""
Alert Generation Service for Weather-based Disruption Alerts (Phase 6).

Generates actionable alerts based on weather conditions and infrastructure risk scores.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from django.utils import timezone

from apps.routes.models import Infrastructure, WeatherSnapshot, District

logger = logging.getLogger(__name__)


class WeatherAlertService:
    """
    Service for generating weather-based infrastructure alerts.
    """
    
    # Alert severity thresholds
    CRITICAL_RISK_THRESHOLD = 80.0
    HIGH_RISK_THRESHOLD = 66.0
    MEDIUM_RISK_THRESHOLD = 36.0
    
    EXTREME_RAINFALL_THRESHOLD = 100.0  # mm in 24h
    HEAVY_RAINFALL_THRESHOLD = 50.0     # mm in 24h
    
    @classmethod
    def generate_infrastructure_alerts(
        cls,
        lat: float = None,
        lng: float = None,
        radius_m: float = 50000,
    ) -> List[Dict[str, Any]]:
        """
        Generate active alerts for infrastructure segments based on current risk levels
        and weather conditions.
        
        Args:
            lat: Optional latitude for proximity filtering
            lng: Optional longitude for proximity filtering
            radius_m: Radius in meters for proximity search (default 50km)
            
        Returns:
            List of alert dictionaries
        """
        alerts = []
        
        # Get high-risk infrastructure
        if lat is not None and lng is not None:
            from django.contrib.gis.geos import Point
            from django.contrib.gis.measure import D
            
            point = Point(lng, lat, srid=4326)
            infrastructure_qs = Infrastructure.objects.filter(
                geom__dwithin=(point, D(m=radius_m)),
                risk_level__in=['high', 'medium']
            )
        else:
            infrastructure_qs = Infrastructure.objects.filter(
                risk_level__in=['high', 'medium']
            )
        
        for infra in infrastructure_qs:
            alert = cls._create_infrastructure_alert(infra)
            if alert:
                alerts.append(alert)
        
        # Sort by severity (critical > high > medium)
        severity_order = {'critical': 0, 'high': 1, 'medium': 2}
        alerts.sort(key=lambda x: severity_order.get(x['severity'], 3))
        
        return alerts
    
    @classmethod
    def _create_infrastructure_alert(cls, infra: Infrastructure) -> Dict[str, Any]:
        """
        Create an alert dictionary for a single infrastructure segment.
        """
        if infra.risk_score < cls.MEDIUM_RISK_THRESHOLD:
            return None
        
        # Determine severity
        if infra.risk_score >= cls.CRITICAL_RISK_THRESHOLD:
            severity = 'critical'
            title_prefix = 'CRITICAL DISRUPTION RISK'
        elif infra.risk_score >= cls.HIGH_RISK_THRESHOLD:
            severity = 'high'
            title_prefix = 'High Disruption Risk'
        else:
            severity = 'medium'
            title_prefix = 'Moderate Disruption Risk'
        
        # Build description from risk factors
        description_parts = [
            f"Risk score {infra.risk_score}/100.",
        ]
        
        if infra.landslide_susceptibility == 'high':
            description_parts.append("Landslide susceptibility HIGH.")
        
        if infra.recent_rainfall_mm >= cls.HEAVY_RAINFALL_THRESHOLD:
            description_parts.append(f"Heavy rainfall {infra.recent_rainfall_mm}mm.")
        elif infra.recent_rainfall_mm >= 20.0:
            description_parts.append(f"Recent rainfall {infra.recent_rainfall_mm}mm.")
        
        if infra.weather_warning:
            description_parts.append("Active weather warning in effect.")
        
        if infra.condition in ['damaged', 'poor']:
            description_parts.append(f"Infrastructure condition: {infra.condition.upper()}.")
        
        # Get location (use first point of LineString)
        location = None
        if infra.geom:
            coords = infra.geom.coords
            if coords:
                first_point = coords[0]
                location = {'lat': first_point[1], 'lng': first_point[0]}
        
        return {
            'alert_id': f'infra-{infra.id}-{infra.risk_level}',
            'type': 'infrastructure_risk',
            'severity': severity,
            'title': f'{title_prefix} — {infra.name}',
            'description': ' '.join(description_parts),
            'infrastructure_id': infra.id,
            'infrastructure_name': infra.name,
            'location': location,
            'risk_score': infra.risk_score,
            'risk_level': infra.risk_level,
            'disruption_probability': infra.disruption_probability,
            'top_factors': infra.top_factors,
            'generated_at': timezone.now().isoformat(),
        }
    
    @classmethod
    def generate_weather_alerts(cls) -> List[Dict[str, Any]]:
        """
        Generate alerts for extreme weather conditions across all districts.
        """
        alerts = []
        
        districts = District.objects.all()
        
        for district in districts:
            latest_weather = district.latest_weather
            
            if not latest_weather:
                continue
            
            # Check for extreme rainfall
            if latest_weather.rainfall_mm >= cls.EXTREME_RAINFALL_THRESHOLD:
                alerts.append({
                    'alert_id': f'weather-{district.id}-extreme-rainfall',
                    'type': 'extreme_weather',
                    'severity': 'critical',
                    'title': f'Extreme Rainfall Alert — {district.name}',
                    'description': f'Extreme rainfall of {latest_weather.rainfall_mm}mm recorded in past 24 hours. '
                                   f'Severe disruption risk for all road segments in the district.',
                    'district_id': district.id,
                    'district_name': district.name,
                    'rainfall_mm': latest_weather.rainfall_mm,
                    'condition': latest_weather.condition,
                    'recorded_at': latest_weather.recorded_at.isoformat(),
                    'generated_at': timezone.now().isoformat(),
                })
            elif latest_weather.rainfall_mm >= cls.HEAVY_RAINFALL_THRESHOLD:
                alerts.append({
                    'alert_id': f'weather-{district.id}-heavy-rainfall',
                    'type': 'heavy_rainfall',
                    'severity': 'high',
                    'title': f'Heavy Rainfall Advisory — {district.name}',
                    'description': f'Heavy rainfall of {latest_weather.rainfall_mm}mm recorded in past 24 hours. '
                                   f'Increased disruption risk on vulnerable road segments.',
                    'district_id': district.id,
                    'district_name': district.name,
                    'rainfall_mm': latest_weather.rainfall_mm,
                    'condition': latest_weather.condition,
                    'recorded_at': latest_weather.recorded_at.isoformat(),
                    'generated_at': timezone.now().isoformat(),
                })
            
            # Check for official weather warnings
            if latest_weather.weather_warning:
                alerts.append({
                    'alert_id': f'weather-{district.id}-warning',
                    'type': 'weather_warning',
                    'severity': 'high',
                    'title': f'Weather Warning — {district.name}',
                    'description': latest_weather.warning_details or 'Official weather warning in effect for this district.',
                    'district_id': district.id,
                    'district_name': district.name,
                    'warning_details': latest_weather.warning_details,
                    'recorded_at': latest_weather.recorded_at.isoformat(),
                    'generated_at': timezone.now().isoformat(),
                })
        
        return alerts
    
    @classmethod
    def generate_all_alerts(
        cls,
        lat: float = None,
        lng: float = None,
        radius_m: float = 50000,
    ) -> Dict[str, Any]:
        """
        Generate all types of alerts (infrastructure + weather).
        
        Returns:
            Dictionary with categorized alerts and summary
        """
        infra_alerts = cls.generate_infrastructure_alerts(lat, lng, radius_m)
        weather_alerts = cls.generate_weather_alerts()
        
        all_alerts = infra_alerts + weather_alerts
        
        # Count by severity
        critical_count = sum(1 for a in all_alerts if a['severity'] == 'critical')
        high_count = sum(1 for a in all_alerts if a['severity'] == 'high')
        medium_count = sum(1 for a in all_alerts if a['severity'] == 'medium')
        
        return {
            'alerts': all_alerts,
            'total_alerts': len(all_alerts),
            'infrastructure_alerts': len(infra_alerts),
            'weather_alerts': len(weather_alerts),
            'severity_breakdown': {
                'critical': critical_count,
                'high': high_count,
                'medium': medium_count,
            },
            'generated_at': timezone.now().isoformat(),
        }
