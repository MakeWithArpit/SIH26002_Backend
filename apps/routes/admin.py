from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from .models import District, Infrastructure, WeatherSnapshot


@admin.register(District)
class DistrictAdmin(GISModelAdmin):
    list_display = ('name', 'state', 'accessibility_score', 'connectivity_status', 'updated_at')
    list_filter = ('state', 'connectivity_status')
    search_fields = ('name', 'state')


@admin.register(Infrastructure)
class InfrastructureAdmin(GISModelAdmin):
    list_display = (
        'name',
        'district',
        'infra_type',
        'road_classification',
        'status',
        'risk_level',
        'risk_score',
        'disruption_probability',
        'length_km',
        'last_assessed_at',
    )
    list_filter = ('infra_type', 'road_classification', 'status', 'risk_level', 'district')
    search_fields = ('name', 'start_node', 'end_node')
    readonly_fields = ('last_assessed_at',)


@admin.register(WeatherSnapshot)
class WeatherSnapshotAdmin(admin.ModelAdmin):
    list_display = ('district', 'condition', 'rainfall_mm', 'temperature_c', 'humidity_pct', 'wind_speed_kmh', 'weather_warning', 'recorded_at')
    list_filter = ('condition', 'weather_warning', 'district')
    search_fields = ('district__name',)
    readonly_fields = ('created_at',)
