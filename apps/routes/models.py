from django.contrib.gis.db import models
from django.contrib.auth.models import User


class AlertType(models.TextChoices):
    INFRASTRUCTURE_RISK = 'infrastructure_risk', 'Infrastructure Risk'
    EXTREME_WEATHER = 'extreme_weather', 'Extreme Weather'
    HEAVY_RAINFALL = 'heavy_rainfall', 'Heavy Rainfall'
    WEATHER_WARNING = 'weather_warning', 'Weather Warning'
    FLOOD_DETECTION = 'flood_detection', 'Flood Detection'
    LANDSLIDE_WARNING = 'landslide_warning', 'Landslide Warning'
    ROAD_BLOCKAGE = 'road_blockage', 'Road Blockage'
    DELIVERY_DELAY = 'delivery_delay', 'Delivery Delay'


class AlertSeverity(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class AlertStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
    RESOLVED = 'resolved', 'Resolved'
    DISMISSED = 'dismissed', 'Dismissed'


class Alert(models.Model):
    """
    Persistent alert records generated from infrastructure risk, weather, and trip conditions.
    Replaces ephemeral alert generation with database-persisted alerts.
    """
    
    # Alert identification
    alert_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique alert identifier (e.g., infra-5-high)"
    )
    alert_type = models.CharField(
        max_length=30,
        choices=AlertType.choices,
        db_index=True,
    )
    
    # Severity & Status
    severity = models.CharField(
        max_length=10,
        choices=AlertSeverity.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.ACTIVE,
        db_index=True,
    )
    
    # Content
    title = models.CharField(max_length=255)
    description = models.TextField()
    recommended_action = models.TextField(blank=True, default='')
    
    # Location (optional - for infrastructure alerts)
    location = models.PointField(srid=4326, geography=True, null=True, blank=True)
    
    # Related entities
    infrastructure = models.ForeignKey(
        'routes.Infrastructure',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='alerts',
    )
    district = models.ForeignKey(
        'routes.District',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='alerts',
    )
    trip = models.ForeignKey(
        'vehicles.Trip',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='alerts',
    )
    
    # Risk metrics at time of alert
    risk_score = models.FloatField(null=True, blank=True)
    risk_level = models.CharField(max_length=10, blank=True, default='')
    disruption_probability = models.FloatField(null=True, blank=True)
    
    # Weather data (if applicable)
    rainfall_mm = models.FloatField(null=True, blank=True)
    weather_condition = models.CharField(max_length=20, blank=True, default='')
    
    # Metadata
    generated_by = models.CharField(
        max_length=50,
        default='system',
        help_text="Source of alert generation (system, celery, manual)"
    )
    
    # Timestamps
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Assigned to
    assigned_to = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_alerts',
    )
    
    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['status', '-generated_at']),
            models.Index(fields=['severity', 'status']),
            models.Index(fields=['alert_type', 'status']),
            models.Index(fields=['district', 'status']),
        ]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title} — {self.get_status_display()}"