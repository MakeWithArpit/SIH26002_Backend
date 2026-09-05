from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from .models import Vehicle, LocationPing, Trip


@admin.register(Vehicle)
class VehicleAdmin(GISModelAdmin):
    list_display = (
        'registration_number',
        'vehicle_type',
        'driver',
        'current_speed',
        'last_ping_time',
        'is_active',
    )
    list_filter = ('vehicle_type', 'is_active')
    search_fields = ('registration_number',)


@admin.register(LocationPing)
class LocationPingAdmin(GISModelAdmin):
    list_display = ('vehicle', 'speed', 'timestamp', 'recorded_at')
    list_filter = ('vehicle',)
    ordering = ('-timestamp',)


@admin.register(Trip)
class TripAdmin(GISModelAdmin):
    list_display = (
        'trip_code',
        'vehicle',
        'driver',
        'origin_name',
        'destination_name',
        'status',
        'base_eta_minutes',
        'predicted_eta_minutes',
        'expected_delay_minutes',
    )
    list_filter = ('status',)
    search_fields = ('trip_code', 'origin_name', 'destination_name')
