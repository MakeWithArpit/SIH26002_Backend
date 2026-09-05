import json
from rest_framework import serializers
from .models import District, Infrastructure


class DistrictSerializer(serializers.ModelSerializer):
    infrastructure_count = serializers.IntegerField(source='infrastructure.count', read_only=True)
    geojson = serializers.SerializerMethodField()

    class Meta:
        model = District
        fields = [
            'id',
            'name',
            'state',
            'accessibility_score',
            'connectivity_status',
            'infrastructure_count',
            'geojson',
            'created_at',
            'updated_at',
        ]

    def get_geojson(self, obj):
        if obj.geom:
            return json.loads(obj.geom.geojson)
        return None


class InfrastructureSerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source='district.name', read_only=True)
    state = serializers.CharField(source='district.state', read_only=True)
    coordinates = serializers.SerializerMethodField()

    class Meta:
        model = Infrastructure
        fields = [
            'id',
            'name',
            'district',
            'district_name',
            'state',
            'infra_type',
            'road_classification',
            'start_node',
            'end_node',
            'length_km',
            'base_speed_kmh',
            'base_travel_time_min',
            'status',
            'condition',
            'landslide_susceptibility',
            'historical_landslide_count',
            'flood_hazard_zone',
            'recent_rainfall_mm',
            'weather_warning',
            'risk_score',
            'disruption_probability',
            'risk_level',
            'top_factors',
            'last_assessed_at',
            'coordinates',
        ]

    def get_coordinates(self, obj):
        """Return list of [lat, lng] points for frontend mapping."""
        if obj.geom:
            # PostGIS LineString coords are (x, y) = (lng, lat)
            return [[pt[1], pt[0]] for pt in obj.geom.coords]
        return []


class InfrastructureRiskAssessSerializer(serializers.Serializer):
    """
    Serializer for simulating or triggering risk recalculation on a segment.
    """
    recent_rainfall_mm = serializers.FloatField(required=False, min_value=0.0)
    weather_warning = serializers.BooleanField(required=False)
    simulate_only = serializers.BooleanField(default=False, help_text="If true, does not persist to DB")
