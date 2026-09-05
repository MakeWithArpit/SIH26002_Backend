"""
Spatial Snap Service — Phase 2 stub.

Phase 2: Use PostGIS ST_DWithin / ST_ClosestPoint to snap the report's
GPS location to the nearest RoadSegment in the road network graph.

Phase 1: No-op — RoadSegment does not exist yet.
"""
import logging

from apps.reports.models import IncidentReport

logger = logging.getLogger(__name__)


def snap(report: IncidentReport) -> None:
    """
    Snap an IncidentReport's location to the nearest RoadSegment.

    Phase 1 stub: does nothing, snapped_road_segment stays NULL.
    Phase 2: populate report.snapped_road_segment via PostGIS query.
    """
    # No-op until Phase 2 delivers the roads app with RoadSegment model.
    logger.debug(
        'Spatial snap skipped for report %s (RoadSegment not yet available)',
        report.pk,
    )
