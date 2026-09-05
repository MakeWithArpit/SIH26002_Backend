from django.contrib.gis.db import models
from django.contrib.auth.models import User


class IncidentType(models.TextChoices):
    FLOOD = 'flood', 'Flood'
    LANDSLIDE = 'landslide', 'Landslide'
    ROAD_DAMAGE = 'road_damage', 'Road Damage'
    OBSTRUCTION = 'obstruction', 'Obstruction'


class SeverityLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class AnalysisStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class ReportStatus(models.TextChoices):
    SUBMITTED = 'submitted', 'Submitted'
    UNDER_REVIEW = 'under_review', 'Under Review'
    RESOLVED = 'resolved', 'Resolved'


class IncidentReport(models.Model):
    """
    A geo-tagged field incident report submitted by a Field Officer.

    Flow:
      Field Officer -> photo + GPS + description
        -> PhotoAnalysisService (CV stub, Phase 5 real model)
        -> SpatialSnapService (Phase 2 stub, snaps to nearest RoadSegment)
        -> IncidentReport persisted with AI result + snapped segment
    """

    # Submitting officer
    officer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='incident_reports',
    )

    # Evidence
    photo = models.ImageField(upload_to='reports/photos/%Y/%m/%d/')

    # Geospatial location (WGS84)
    location = models.PointField(srid=4326, geography=True)

    # Road segment this report snaps to (populated by SpatialSnapService in Phase 2)
    # Phase 1: plain integer placeholder — replaced with FK to RoadSegment in Phase 2
    snapped_road_segment_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text='ID of the nearest RoadSegment (Phase 2 FK).',
    )

    # Officer-provided fields
    description = models.TextField(blank=True, default='')
    incident_type = models.CharField(
        max_length=20,
        choices=IncidentType.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=10,
        choices=SeverityLevel.choices,
        db_index=True,
    )

    # Timestamps
    client_timestamp = models.DateTimeField(
        help_text='Device timestamp from the mobile app.'
    )
    server_timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text='Server receipt timestamp.',
    )

    # AI / CV analysis result (populated synchronously after create)
    ai_issue_type = models.CharField(max_length=20, blank=True, default='')
    ai_severity = models.CharField(max_length=10, blank=True, default='')
    ai_confidence = models.FloatField(null=True, blank=True)
    analysis_status = models.CharField(
        max_length=20,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
        db_index=True,
    )

    # Report lifecycle
    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.SUBMITTED,
        db_index=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-server_timestamp']
        verbose_name = 'Incident Report'
        verbose_name_plural = 'Incident Reports'

    def __str__(self):
        return f"[{self.get_incident_type_display()}] {self.officer.username} @ {self.server_timestamp:%Y-%m-%d %H:%M}"
