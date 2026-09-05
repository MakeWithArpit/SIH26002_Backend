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


class RouteCandidateSerializer(serializers.Serializer):
    route_id = serializers.CharField()
    name = serializers.CharField()
    distance_km = serializers.FloatField()
    base_eta_minutes = serializers.FloatField()
    risk_score = serializers.FloatField()
    risk_level = serializers.CharField()
    recommended = serializers.BooleanField()
    explanation = serializers.CharField()
    polyline = serializers.ListField(child=serializers.ListField(child=serializers.FloatField()))
    segments = serializers.ListField(child=serializers.DictField())


class RouteCalculationRequestSerializer(serializers.Serializer):
    """
    Accepts lat/lng coordinates or direct graph node IDs.
    """
    origin_lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    origin_lng = serializers.FloatField(required=False, min_value=-180, max_value=180)
    destination_lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    destination_lng = serializers.FloatField(required=False, min_value=-180, max_value=180)

    origin_node = serializers.CharField(required=False)
    destination_node = serializers.CharField(required=False)

    def validate(self, data):
        has_origin_coords = 'origin_lat' in data and 'origin_lng' in data
        has_origin_node = 'origin_node' in data and data['origin_node']

        if not (has_origin_coords or has_origin_node):
            raise serializers.ValidationError(
                "Either (origin_lat, origin_lng) or origin_node must be provided."
            )

        has_dest_coords = 'destination_lat' in data and 'destination_lng' in data
        has_dest_node = 'destination_node' in data and data['destination_node']

        if not (has_dest_coords or has_dest_node):
            raise serializers.ValidationError(
                "Either (destination_lat, destination_lng) or destination_node must be provided."
            )

        return data

