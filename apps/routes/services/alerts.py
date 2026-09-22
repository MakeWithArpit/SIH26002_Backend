"""
Alert Generation Service for Weather-based Disruption Alerts (Phase 6, 8).

Generates actionable alerts based on weather conditions and infrastructure risk scores.
Persists alerts to database for tracking and resolution.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from django.utils import timezone

from apps.routes.models import Infrastructure, WeatherSnapshot, District, Alert, AlertType, AlertSeverity, AlertStatus

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
            recommended_action = 'Immediate detour recommended. Dispatch ground team for road stability assessment.'
        elif infra.risk_score >= cls.HIGH_RISK_THRESHOLD:
            severity = 'high'
            title_prefix = 'High Disruption Risk'
            recommended_action = 'Exercise high caution. Reduce convoy speed and monitor real-time road conditions.'
        else:
            severity = 'medium'
            title_prefix = 'Moderate Disruption Risk'
            recommended_action = 'Drive with caution. Vulnerable to degradation during precipitation.'
        
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
            'recommended_action': recommended_action,
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
                    'recommended_action': 'Suspend non-essential logistics movement. Prepare landslide and flood hazard protocols.',
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
                    'recommended_action': 'Monitor route accessibility. Field teams should verify road passability.',
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
                    'recommended_action': 'Adhere to official district administration and IMD safety advisories.',
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


class AlertService(WeatherAlertService):
    """
    Service for generating and persisting infrastructure and weather alerts (Phase 8).
    Inherits alert generation rules from WeatherAlertService and adds database persistence.
    """
    
    @classmethod
    def generate_and_persist_alerts(cls) -> Dict[str, Any]:
        """
        Generate alerts from current conditions and persist to database.
        Returns summary of created alerts.
        """
        infra_alerts = cls.generate_infrastructure_alerts()
        weather_alerts = cls.generate_weather_alerts()
        
        created_count = 0
        for alert_data in infra_alerts + weather_alerts:
            if cls._persist_alert(alert_data):
                created_count += 1
        
        return {
            'total_generated': len(infra_alerts) + len(weather_alerts),
            'persisted': created_count,
            'infrastructure_alerts': len(infra_alerts),
            'weather_alerts': len(weather_alerts),
        }
    
    @classmethod
    def _persist_alert(cls, alert_data: Dict[str, Any]) -> bool:
        """
        Persist a single alert to database.
        Returns True if created, False if already exists or error.
        """
        try:
            alert_id = alert_data.get('alert_id')
            
            # Check if alert already exists
            existing = Alert.objects.filter(alert_id=alert_id, status=AlertStatus.ACTIVE).first()
            if existing:
                return False
            
            # Parse severity
            severity_map = {
                'critical': AlertSeverity.CRITICAL,
                'high': AlertSeverity.HIGH,
                'medium': AlertSeverity.MEDIUM,
                'low': AlertSeverity.LOW,
            }
            severity = severity_map.get(alert_data.get('severity', 'medium'), AlertSeverity.MEDIUM)
            
            # Parse alert type
            type_map = {
                'infrastructure_risk': AlertType.INFRASTRUCTURE_RISK,
                'extreme_weather': AlertType.EXTREME_WEATHER,
                'heavy_rainfall': AlertType.HEAVY_RAINFALL,
                'weather_warning': AlertType.WEATHER_WARNING,
                'flood_detection': AlertType.FLOOD_DETECTION,
                'landslide_warning': AlertType.LANDSLIDE_WARNING,
                'road_blockage': AlertType.ROAD_BLOCKAGE,
                'delivery_delay': AlertType.DELIVERY_DELAY,
            }
            alert_type = type_map.get(alert_data.get('type', 'infrastructure_risk'), AlertType.INFRASTRUCTURE_RISK)
            
            # Get related entities
            infra = None
            district = None
            if alert_data.get('infrastructure_id'):
                infra = Infrastructure.objects.filter(id=alert_data['infrastructure_id']).first()
                if infra:
                    district = infra.district
            elif alert_data.get('district_id'):
                district = District.objects.filter(id=alert_data['district_id']).first()

            # Get location
            location = None
            if alert_data.get('location'):
                from django.contrib.gis.geos import Point
                loc = alert_data['location']
                location = Point(loc['lng'], loc['lat'], srid=4326)
            elif district and district.geom:
                from django.contrib.gis.geos import Point
                pt = district.geom.point_on_surface or district.geom.centroid
                if pt:
                    location = Point(pt.x, pt.y, srid=4326)
            
            Alert.objects.create(
                alert_id=alert_id,
                alert_type=alert_type,
                severity=severity,
                status=AlertStatus.ACTIVE,
                title=alert_data.get('title', ''),
                description=alert_data.get('description', ''),
                recommended_action=alert_data.get('recommended_action', ''),
                location=location,
                infrastructure=infra,
                district=district,
                risk_score=alert_data.get('risk_score'),
                risk_level=alert_data.get('risk_level', ''),
                disruption_probability=alert_data.get('disruption_probability'),
                rainfall_mm=alert_data.get('rainfall_mm'),
                generated_by='system',
            )
            return True
        except Exception as e:
            logger.error(f"Failed to persist alert: {e}", exc_info=True)
            return False
    
    @classmethod
    def get_active_alerts(cls, lat=None, lng=None, radius_m=50000) -> List[Alert]:
        """
        Get active alerts from database, optionally filtered by proximity.
        """
        qs = Alert.objects.filter(status=AlertStatus.ACTIVE)
        
        if lat is not None and lng is not None:
            from django.contrib.gis.geos import Point
            from django.contrib.gis.measure import D
            point = Point(lng, lat, srid=4326)
            qs = qs.filter(location__dwithin=(point, D(m=radius_m)))
        
        return list(qs)
    
    @classmethod
    def acknowledge_alert(cls, alert_id: str, user) -> bool:
        """Acknowledge an alert."""
        try:
            alert = Alert.objects.get(alert_id=alert_id)
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = timezone.now()
            alert.assigned_to = user
            alert.save()
            return True
        except Alert.DoesNotExist:
            return False
    
    @classmethod
    def resolve_alert(cls, alert_id: str) -> bool:
        """Resolve an alert."""
        try:
            alert = Alert.objects.get(alert_id=alert_id)
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = timezone.now()
            alert.save()
            return True
        except Alert.DoesNotExist:
            return False
    
    @classmethod
    def get_alert_summary(cls) -> Dict[str, Any]:
        """Get summary counts by severity and status."""
        return {
            'total': Alert.objects.count(),
            'active': Alert.objects.filter(status=AlertStatus.ACTIVE).count(),
            'acknowledged': Alert.objects.filter(status=AlertStatus.ACKNOWLEDGED).count(),
            'resolved': Alert.objects.filter(status=AlertStatus.RESOLVED).count(),
            'critical': Alert.objects.filter(severity=AlertSeverity.CRITICAL, status=AlertStatus.ACTIVE).count(),
            'high': Alert.objects.filter(severity=AlertSeverity.HIGH, status=AlertStatus.ACTIVE).count(),
        }
