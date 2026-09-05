from django.contrib.gis.db import models


class ConnectivityStatus(models.TextChoices):
    NORMAL = 'normal', 'Normal'
    DEGRADED = 'degraded', 'Degraded'
    CRITICAL = 'critical', 'Critical'


class InfrastructureType(models.TextChoices):
    ROAD = 'road', 'Road'
    BRIDGE = 'bridge', 'Bridge'
    CULVERT = 'culvert', 'Culvert'
    TUNNEL = 'tunnel', 'Tunnel'


class RoadClassification(models.TextChoices):
    NATIONAL_HIGHWAY = 'national_highway', 'National Highway'
    STATE_HIGHWAY = 'state_highway', 'State Highway'
    MAJOR_DISTRICT_ROAD = 'major_district_road', 'Major District Road'
    RURAL_ROAD = 'rural_road', 'Rural Road'


class OperationalStatus(models.TextChoices):
    ACCESSIBLE = 'accessible', 'Accessible'
    RISKY = 'risky', 'Risky'
    BLOCKED = 'blocked', 'Blocked'


class PhysicalCondition(models.TextChoices):
    GOOD = 'good', 'Good'
    MODERATE = 'moderate', 'Moderate'
    POOR = 'poor', 'Poor'
    DAMAGED = 'damaged', 'Damaged'


class HazardLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'


class RiskLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'


class District(models.Model):
    """
    District administrative boundary and accessibility indicator.
    """
    name = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=100)
    geom = models.MultiPolygonField(srid=4326, geography=True)
    accessibility_score = models.FloatField(default=10.0, help_text="Accessibility index (0.0 to 10.0)")
    connectivity_status = models.CharField(
        max_length=20,
        choices=ConnectivityStatus.choices,
        default=ConnectivityStatus.NORMAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name}, {self.state}"


class Infrastructure(models.Model):
    """
    Central road network entity (RoadSegment, bridge, culvert, etc.).
    All intelligence (disruption risk, weather, incident photos) attaches here.
    """
    district = models.ForeignKey(
        District,
        on_delete=models.CASCADE,
        related_name='infrastructure',
    )
    name = models.CharField(max_length=255)
    infra_type = models.CharField(
        max_length=20,
        choices=InfrastructureType.choices,
        default=InfrastructureType.ROAD,
        db_index=True,
    )
    road_classification = models.CharField(
        max_length=30,
        choices=RoadClassification.choices,
        default=RoadClassification.NATIONAL_HIGHWAY,
    )
    geom = models.LineStringField(srid=4326, geography=True)

    # Graph connectivity nodes for routing
    start_node = models.CharField(max_length=100, db_index=True)
    end_node = models.CharField(max_length=100, db_index=True)

    # Physical properties
    length_km = models.FloatField(default=0.0)
    base_speed_kmh = models.FloatField(default=50.0)
    base_travel_time_min = models.FloatField(default=0.0)

    # Operational status & physical condition
    status = models.CharField(
        max_length=20,
        choices=OperationalStatus.choices,
        default=OperationalStatus.ACCESSIBLE,
        db_index=True,
    )
    condition = models.CharField(
        max_length=20,
        choices=PhysicalCondition.choices,
        default=PhysicalCondition.GOOD,
    )

    # Static hazard attributes
    landslide_susceptibility = models.CharField(
        max_length=10,
        choices=HazardLevel.choices,
        default=HazardLevel.LOW,
    )
    historical_landslide_count = models.PositiveIntegerField(default=0)
    flood_hazard_zone = models.CharField(
        max_length=10,
        choices=HazardLevel.choices,
        default=HazardLevel.LOW,
    )

    # Dynamic conditions
    recent_rainfall_mm = models.FloatField(default=0.0)
    weather_warning = models.BooleanField(default=False)

    # Calculated Disruption Risk (AI-01 interface)
    risk_score = models.FloatField(default=0.0, help_text="0 to 100 risk score", db_index=True)
    disruption_probability = models.FloatField(default=0.0, help_text="0.0 to 1.0 probability")
    risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.LOW,
        db_index=True,
    )
    top_factors = models.JSONField(default=list, blank=True)
    last_assessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Infrastructure Segment'
        verbose_name_plural = 'Infrastructure Segments'
        ordering = ['name']
        indexes = [
            models.Index(fields=['district', 'status', 'risk_level']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_infra_type_display()}) — {self.risk_level.upper()}"

    def save(self, *args, **kwargs):
        # Auto-compute base travel time if not set
        if self.base_speed_kmh > 0 and (not self.base_travel_time_min or self.base_travel_time_min <= 0):
            self.base_travel_time_min = round((self.length_km / self.base_speed_kmh) * 60.0, 2)
        super().save(*args, **kwargs)
