from rest_framework import serializers
from django.contrib.gis.geos import Point

from .models import IncidentReport


class IncidentReportCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for submitting a new incident report.
    Accepts latitude/longitude as separate fields and constructs
    a GeoDjango Point internally.
    """
    latitude = serializers.FloatField(write_only=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(write_only=True, min_value=-180, max_value=180)

    class Meta:
        model = IncidentReport
        fields = [
            'photo',
            'latitude',
            'longitude',
            'description',
            'incident_type',
            'severity',
            'client_timestamp',
        ]

    def create(self, validated_data):
        lat = validated_data.pop('latitude')
        lng = validated_data.pop('longitude')
        validated_data['location'] = Point(lng, lat, srid=4326)
        validated_data['officer'] = self.context['request'].user
        return super().create(validated_data)


class IncidentReportSerializer(serializers.ModelSerializer):
    """
    Read serializer — returns all report fields including AI results.
    Exposes latitude/longitude extracted from the PointField for
    easy consumption by mobile/frontend clients.
    """
    officer_username = serializers.CharField(source='officer.username', read_only=True)
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    class Meta:
        model = IncidentReport
        fields = [
            'id',
            'officer',
            'officer_username',
            'photo',
            'latitude',
            'longitude',
            'description',
            'incident_type',
            'severity',
            'client_timestamp',
            'server_timestamp',
            'ai_issue_type',
            'ai_severity',
            'ai_confidence',
            'analysis_status',
            'status',
            'snapped_road_segment_id',
            'updated_at',
        ]
        read_only_fields = fields

    def get_latitude(self, obj):
        return obj.location.y if obj.location else None

    def get_longitude(self, obj):
        return obj.location.x if obj.location else None
