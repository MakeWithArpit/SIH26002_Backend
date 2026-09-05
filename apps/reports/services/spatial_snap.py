"""
Spatial Snap Service — Phase 2 implementation.
Snaps IncidentReport's GPS location to the nearest Infrastructure segment
via PostGIS ST_DWithin / Distance, and triggers risk recalculation.
"""
import logging
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance

from apps.reports.models import IncidentReport
from apps.routes.models import Infrastructure
from apps.routes.services.risk import RiskPredictionService

logger = logging.getLogger(__name__)


def snap(report: IncidentReport) -> None:
    """
    Snap an IncidentReport's location to the nearest Infrastructure segment.
    If an infrastructure segment is found within 1000m (or nearest), link it
    and trigger risk recalculation.
    """
    if not report.location:
        return

    # 1. Look for infrastructure within 1km buffer
    nearest = Infrastructure.objects.filter(
        geom__dwithin=(report.location, D(m=1000))
    ).annotate(
        dist=Distance('geom', report.location)
    ).order_by('dist').first()

    # 2. Fallback to closest overall infrastructure if not in 1km buffer
    if not nearest:
        nearest = Infrastructure.objects.annotate(
            dist=Distance('geom', report.location)
        ).order_by('dist').first()

    if nearest:
        report.snapped_infrastructure = nearest
        report.save(update_fields=['snapped_infrastructure'])
        # Recalculate disruption risk with this newly associated incident report
        RiskPredictionService.assess_and_update(nearest)
        logger.info(
            'Report %s snapped to %s (id=%s). Risk updated to %s (%s).',
            report.pk,
            nearest.name,
            nearest.pk,
            nearest.risk_level,
            nearest.risk_score,
        )
