"""
Phase 9 — Offline Sync: Serializers

Validates incoming batch sync payload records.
Two record types are supported:
  - incident_report
  - location_ping
"""
import uuid
from rest_framework import serializers


class IncidentReportSyncSerializer(serializers.Serializer):
    """Validates the `data` dict for an offline incident report record."""
    photo_url = serializers.URLField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    description = serializers.CharField(default='', allow_blank=True)
    incident_type = serializers.ChoiceField(choices=[
        'flood', 'landslide', 'road_damage', 'obstruction'
    ])
    severity = serializers.ChoiceField(choices=[
        'low', 'medium', 'high', 'critical'
    ])
    client_timestamp = serializers.DateTimeField()


class LocationPingSyncSerializer(serializers.Serializer):
    """Validates the `data` dict for an offline location ping record."""
    vehicle_id = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    speed = serializers.FloatField(default=0.0)
    timestamp = serializers.DateTimeField()


class SyncRecordSerializer(serializers.Serializer):
    """Validates a single record in a batch sync payload."""
    client_id = serializers.UUIDField()
    record_type = serializers.ChoiceField(choices=['incident_report', 'location_ping'])
    client_timestamp = serializers.DateTimeField()
    data = serializers.DictField()

    def validate(self, attrs):
        record_type = attrs.get('record_type')
        data = attrs.get('data', {})

        if record_type == 'incident_report':
            s = IncidentReportSyncSerializer(data=data)
            if not s.is_valid():
                raise serializers.ValidationError({'data': s.errors})
        elif record_type == 'location_ping':
            s = LocationPingSyncSerializer(data=data)
            if not s.is_valid():
                raise serializers.ValidationError({'data': s.errors})

        return attrs


class SyncBatchSerializer(serializers.Serializer):
    """Top-level batch sync payload."""
    records = SyncRecordSerializer(many=True)

    def validate_records(self, records):
        if not records:
            raise serializers.ValidationError('Batch must contain at least one record.')
        if len(records) > 500:
            raise serializers.ValidationError('Batch must not exceed 500 records.')
        return records
