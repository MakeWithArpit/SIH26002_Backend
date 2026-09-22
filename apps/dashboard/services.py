"""
Phase 11 — Dashboard Aggregation APIs: DashboardService

Read-only aggregation queries served from existing domain tables.
No new DB models introduced (architecture rule).
"""
import logging
from typing import Any, Dict

from django.db.models import Avg, Count, Q, Max
from django.utils import timezone

from apps.reports.models import IncidentReport, ReportStatus
from apps.routes.models import (
    Alert, AlertStatus, AlertSeverity,
    District, Infrastructure, OperationalStatus, RiskLevel, ConnectivityStatus,
)
from apps.vehicles.models import Vehicle, Trip, TripStatus

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Aggregation queries for the dashboard API layer.
    All methods return serialisable dicts — no model instances.
    """

    def get_summary(self) -> Dict[str, Any]:
        """
        Top-level operational KPIs for the main dashboard header.
        """
        total_districts = District.objects.count()
        total_infra = Infrastructure.objects.count()
        blocked_infra = Infrastructure.objects.filter(status=OperationalStatus.BLOCKED).count()
        high_risk_infra = Infrastructure.objects.filter(risk_level=RiskLevel.HIGH).count()

        active_alerts = Alert.objects.filter(status=AlertStatus.ACTIVE).count()
        critical_alerts = Alert.objects.filter(
            status=AlertStatus.ACTIVE, severity=AlertSeverity.CRITICAL
        ).count()

        active_vehicles = Vehicle.objects.filter(is_active=True).count()
        on_route_trips = Trip.objects.filter(status=TripStatus.ON_ROUTE).count()
        at_risk_trips = Trip.objects.filter(status=TripStatus.AT_RISK).count()

        pending_reports = IncidentReport.objects.filter(
            status=ReportStatus.SUBMITTED
        ).count()

        critical_districts = District.objects.filter(
            connectivity_status=ConnectivityStatus.CRITICAL
        ).count()

        return {
            'districts': {
                'total': total_districts,
                'critical_connectivity': critical_districts,
            },
            'infrastructure': {
                'total': total_infra,
                'blocked': blocked_infra,
                'high_risk': high_risk_infra,
            },
            'alerts': {
                'active': active_alerts,
                'critical': critical_alerts,
            },
            'vehicles': {
                'active': active_vehicles,
                'on_route': on_route_trips,
                'at_risk': at_risk_trips,
            },
            'field_reports': {
                'pending': pending_reports,
            },
            'generated_at': timezone.now().isoformat(),
        }

    def get_districts_overview(self) -> Dict[str, Any]:
        """
        Per-district overview: risk, accessibility, connectivity, weather.
        """
        districts = District.objects.all().order_by('name')
        result = []
        for d in districts:
            infra_qs = d.infrastructure.all()
            avg_risk = infra_qs.aggregate(avg=Avg('risk_score'))['avg'] or 0.0
            blocked = infra_qs.filter(status=OperationalStatus.BLOCKED).count()
            latest_w = d.latest_weather
            result.append({
                'id': d.pk,
                'name': d.name,
                'state': d.state,
                'accessibility_score': d.accessibility_score,
                'connectivity_status': d.connectivity_status,
                'avg_risk_score': round(avg_risk, 1),
                'blocked_segments': blocked,
                'total_segments': infra_qs.count(),
                'active_alerts': d.alerts.filter(status=AlertStatus.ACTIVE).count(),
                'weather': {
                    'condition': latest_w.condition if latest_w else None,
                    'rainfall_mm': latest_w.rainfall_mm if latest_w else None,
                    'weather_warning': latest_w.weather_warning if latest_w else False,
                },
            })
        return {'districts': result, 'total': len(result)}

    def get_vehicles_summary(self) -> Dict[str, Any]:
        """
        Fleet operational summary grouped by status.
        """
        vehicles = Vehicle.objects.filter(is_active=True).values(
            'pk', 'registration_number', 'vehicle_type',
            'current_lat', 'current_lng', 'current_speed', 'last_ping_time'
        )
        trip_counts = (
            Trip.objects.values('status')
            .annotate(count=Count('id'))
        )
        by_status = {row['status']: row['count'] for row in trip_counts}

        return {
            'total_active_vehicles': vehicles.count(),
            'trips_by_status': by_status,
            'vehicles': list(vehicles),
        }

    def get_active_alerts_feed(self, limit: int = 50) -> Dict[str, Any]:
        """
        Active and critical alerts feed, newest first, capped at `limit`.
        """
        alerts = (
            Alert.objects.filter(status=AlertStatus.ACTIVE)
            .select_related('district', 'infrastructure')
            .order_by('-generated_at')[:limit]
        )
        return {
            'alerts': [
                {
                    'id': a.pk,
                    'alert_id': a.alert_id,
                    'type': a.alert_type,
                    'severity': a.severity,
                    'title': a.title,
                    'description': a.description,
                    'recommended_action': a.recommended_action,
                    'district': a.district.name if a.district else None,
                    'infrastructure': a.infrastructure.name if a.infrastructure else None,
                    'generated_at': a.generated_at.isoformat(),
                }
                for a in alerts
            ],
            'total': Alert.objects.filter(status=AlertStatus.ACTIVE).count(),
        }

    def get_bottlenecks(self, top_n: int = 20) -> Dict[str, Any]:
        """
        Top N high-risk or blocked infrastructure segments.
        """
        segments = (
            Infrastructure.objects.filter(
                Q(status=OperationalStatus.BLOCKED) |
                Q(risk_level=RiskLevel.HIGH) |
                Q(risk_score__gte=60)
            )
            .select_related('district')
            .order_by('-risk_score')[:top_n]
        )
        return {
            'bottlenecks': [
                {
                    'id': s.pk,
                    'name': s.name,
                    'type': s.infra_type,
                    'status': s.status,
                    'risk_score': s.risk_score,
                    'risk_level': s.risk_level,
                    'disruption_probability': s.disruption_probability,
                    'district': s.district.name,
                    'top_factors': s.top_factors,
                }
                for s in segments
            ],
            'total': segments.count(),
        }

    def get_field_intelligence_summary(self, limit: int = 30) -> Dict[str, Any]:
        """
        Recent field incident reports for situational awareness.
        """
        reports = (
            IncidentReport.objects.select_related('officer', 'snapped_infrastructure')
            .order_by('-server_timestamp')[:limit]
        )
        by_type = (
            IncidentReport.objects.values('incident_type')
            .annotate(count=Count('id'))
        )
        by_severity = (
            IncidentReport.objects.values('severity')
            .annotate(count=Count('id'))
        )

        return {
            'recent_reports': [
                {
                    'id': r.pk,
                    'incident_type': r.incident_type,
                    'severity': r.severity,
                    'description': r.description[:120] if r.description else '',
                    'status': r.status,
                    'officer': r.officer.username,
                    'analysis_status': r.analysis_status,
                    'ai_issue_type': r.ai_issue_type,
                    'ai_severity': r.ai_severity,
                    'snapped_segment': (
                        r.snapped_infrastructure.name
                        if r.snapped_infrastructure else None
                    ),
                    'server_timestamp': r.server_timestamp.isoformat(),
                }
                for r in reports
            ],
            'by_type': {row['incident_type']: row['count'] for row in by_type},
            'by_severity': {row['severity']: row['count'] for row in by_severity},
            'total': IncidentReport.objects.count(),
        }
