from django.contrib.gis.db import models
from django.contrib.auth.models import User


class VehicleType(models.TextChoices):
    TRUCK = 'truck', 'Heavy Truck'
    VAN = 'van', 'Delivery Van'
    EMERGENCY = 'emergency', 'Emergency / Relief Vehicle'
    CAR = 'car', 'Light Vehicle / Car'


class TripStatus(models.TextChoices):
    CREATED = 'created', 'Created'
    ON_ROUTE = 'on_route', 'On Route'
    DELAYED = 'delayed', 'Delayed'
    AT_RISK = 'at_risk', 'At Risk'
    DELIVERED = 'delivered', 'Delivered'


class Vehicle(models.Model):
    """
    Fleet vehicle record.
    Maintains cached current tracking fields for O(1) polling
    without scanning the full LocationPing history table.
    """
    registration_number = models.CharField(max_length=30, unique=True, db_index=True)
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.TRUCK,
    )
    driver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicles',
    )
    capacity_tons = models.FloatField(default=5.0)

    # Cached current telemetry (updated atomically on every LocationPing)
    current_lat = models.FloatField(null=True, blank=True)
    current_lng = models.FloatField(null=True, blank=True)
    current_speed = models.FloatField(default=0.0, help_text="Speed in km/h")
    last_ping_time = models.DateTimeField(null=True, blank=True)
    current_location = models.PointField(srid=4326, geography=True, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['registration_number']

    def __str__(self):
        return f"{self.registration_number} ({self.get_vehicle_type_display()})"


class LocationPing(models.Model):
    """
    Historical location telemetry received from the mobile app via REST.
    No dedicated GPS hardware or MQTT required for MVP.
    """
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='location_pings',
    )
    location = models.PointField(srid=4326, geography=True)
    speed = models.FloatField(default=0.0, help_text="Speed in km/h")
    timestamp = models.DateTimeField(db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['vehicle', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.vehicle.registration_number} @ {self.timestamp.isoformat()} ({self.speed} km/h)"


class Trip(models.Model):
    """
    Logistics delivery mission connecting origin to destination.
    Maintains condition-aware ETA and expected delay (AI-02).
    """
    trip_code = models.CharField(max_length=50, unique=True, db_index=True)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='trips',
    )
    driver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trips',
    )
    origin = models.PointField(srid=4326, geography=True)
    origin_name = models.CharField(max_length=255)
    destination = models.PointField(srid=4326, geography=True)
    destination_name = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=TripStatus.choices,
        default=TripStatus.CREATED,
        db_index=True,
    )
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    # Condition-Aware ETA & Delay (AI-02 interface)
    base_eta_minutes = models.FloatField(default=0.0)
    predicted_eta_minutes = models.FloatField(default=0.0)
    expected_delay_minutes = models.FloatField(default=0.0)
    eta_factors = models.JSONField(default=list, blank=True)
    last_eta_updated_at = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vehicle', 'status']),
        ]

    def __str__(self):
        return f"Trip {self.trip_code}: {self.origin_name} -> {self.destination_name} [{self.get_status_display()}]"
