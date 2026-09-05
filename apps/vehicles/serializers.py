from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import Vehicle, LocationPing, Trip


class VehicleSerializer(serializers.ModelSerializer):
    driver_username = serializers.CharField(source='driver.username', read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id',
            'registration_number',
            'vehicle_type',
            'driver',
            'driver_username',
            'capacity_tons',
            'current_lat',
            'current_lng',
            'current_speed',
            'last_ping_time',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['current_lat', 'current_lng', 'last_ping_time', 'created_at', 'updated_at']


class LocationPingCreateSerializer(serializers.Serializer):
    """
    Serializer for REST location pings from driver mobile app.
    """
    lat = serializers.FloatField(min_value=-90.0, max_value=90.0)
    lng = serializers.FloatField(min_value=-180.0, max_value=180.0)
    speed = serializers.FloatField(default=0.0, min_value=0.0)
    timestamp = serializers.DateTimeField()


class LocationPingSerializer(serializers.ModelSerializer):
    lat = serializers.SerializerMethodField()
    lng = serializers.SerializerMethodField()

    class Meta:
        model = LocationPing
        fields = ['id', 'vehicle', 'lat', 'lng', 'speed', 'timestamp', 'recorded_at']

    def get_lat(self, obj):
        return obj.location.y if obj.location else None

    def get_lng(self, obj):
        return obj.location.x if obj.location else None


class TripCreateSerializer(serializers.ModelSerializer):
    origin_lat = serializers.FloatField(write_only=True, min_value=-90.0, max_value=90.0)
    origin_lng = serializers.FloatField(write_only=True, min_value=-180.0, max_value=180.0)
    destination_lat = serializers.FloatField(write_only=True, min_value=-90.0, max_value=90.0)
    destination_lng = serializers.FloatField(write_only=True, min_value=-180.0, max_value=180.0)

    class Meta:
        model = Trip
        fields = [
            'trip_code',
            'vehicle',
            'origin_name',
            'origin_lat',
            'origin_lng',
            'destination_name',
            'destination_lat',
            'destination_lng',
        ]

    def create(self, validated_data):
        origin_lat = validated_data.pop('origin_lat')
        origin_lng = validated_data.pop('origin_lng')
        dest_lat = validated_data.pop('destination_lat')
        dest_lng = validated_data.pop('destination_lng')

        validated_data['origin'] = Point(origin_lng, origin_lat, srid=4326)
        validated_data['destination'] = Point(dest_lng, dest_lat, srid=4326)

        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['driver'] = request.user

        return super().create(validated_data)


class TripSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)
    driver_username = serializers.CharField(source='driver.username', read_only=True)
    origin_coords = serializers.SerializerMethodField()
    destination_coords = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            'id',
            'trip_code',
            'vehicle',
            'vehicle_registration',
            'driver',
            'driver_username',
            'origin_name',
            'origin_coords',
            'destination_name',
            'destination_coords',
            'status',
            'start_time',
            'end_time',
            'base_eta_minutes',
            'predicted_eta_minutes',
            'expected_delay_minutes',
            'eta_factors',
            'last_eta_updated_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_origin_coords(self, obj):
        if obj.origin:
            return {'lat': obj.origin.y, 'lng': obj.origin.x}
        return None

    def get_destination_coords(self, obj):
        if obj.destination:
            return {'lat': obj.destination.y, 'lng': obj.destination.x}
        return None
