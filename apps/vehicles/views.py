from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.contrib.gis.geos import Point
from django.utils import timezone

from apps.accounts.permissions import IsAdminRole
from apps.common.responses import standard_response
from .models import Vehicle, LocationPing, Trip, TripStatus
from .serializers import (
    VehicleSerializer,
    LocationPingCreateSerializer,
    LocationPingSerializer,
    TripSerializer,
    TripCreateSerializer,
)
from .services.eta import ETAEstimationService


class VehicleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for fleet vehicles.
    - All authenticated users can list and retrieve.
    - Drivers/mobile apps ingest location pings at /vehicles/{id}/locations/.
    - Real-time latest location is O(1) polled at /vehicles/{id}/location/latest/.
    """
    queryset = Vehicle.objects.select_related('driver').all()
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminRole()]
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return standard_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return standard_response(data=serializer.data)

    @action(detail=True, methods=['post'], url_path='locations')
    def ingest_location(self, request, pk=None):
        """
        Ingests REST location ping from driver mobile app.
        Atomically saves historical LocationPing and updates cached Vehicle fields.
        """
        vehicle = self.get_object()
        serializer = LocationPingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vdata = serializer.validated_data

        lat = vdata['lat']
        lng = vdata['lng']
        speed = vdata.get('speed', 0.0)
        timestamp = vdata['timestamp']
        point = Point(lng, lat, srid=4326)

        with transaction.atomic():
            # 1. Create historical telemetry record
            ping = LocationPing.objects.create(
                vehicle=vehicle,
                location=point,
                speed=speed,
                timestamp=timestamp,
            )

            # 2. Atomically update cached vehicle telemetry for O(1) dashboard polling
            vehicle.current_lat = lat
            vehicle.current_lng = lng
            vehicle.current_speed = speed
            vehicle.last_ping_time = timestamp
            vehicle.current_location = point
            vehicle.save(update_fields=[
                'current_lat',
                'current_lng',
                'current_speed',
                'last_ping_time',
                'current_location',
                'updated_at',
            ])

            # 3. If vehicle has an active trip on_route, re-evaluate ETA
            active_trip = vehicle.trips.filter(status=TripStatus.ON_ROUTE).first()
            if active_trip:
                ETAEstimationService.update_trip_eta(active_trip)

        return standard_response(
            data={
                'ping_id': ping.id,
                'vehicle_registration': vehicle.registration_number,
                'current_lat': lat,
                'current_lng': lng,
                'speed': speed,
                'timestamp': timestamp.isoformat(),
            },
            message="Location ping ingested and telemetry updated successfully.",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='location/latest')
    def latest_location(self, request, pk=None):
        """
        O(1) retrieval of latest vehicle location from cached fields.
        Eliminates full-table scans of LocationPing on repeated 10-15s polling.
        """
        vehicle = self.get_object()
        if not vehicle.last_ping_time:
            return standard_response(
                data=None,
                message="No location telemetry recorded for this vehicle yet.",
            )

        return standard_response(
            data={
                'vehicle_id': vehicle.id,
                'registration_number': vehicle.registration_number,
                'lat': vehicle.current_lat,
                'lng': vehicle.current_lng,
                'speed': vehicle.current_speed,
                'last_ping_time': vehicle.last_ping_time.isoformat(),
            },
            message="Latest location retrieved successfully.",
        )


class TripViewSet(viewsets.ModelViewSet):
    """
    Logistics delivery trips with condition-aware ETA (AI-02).
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return TripCreateSerializer
        return TripSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Trip.objects.select_related('vehicle', 'driver').all()
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin_role):
            return qs
        return qs.filter(driver=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        trip = serializer.save()

        # Compute initial ETA
        ETAEstimationService.update_trip_eta(trip)
        trip.refresh_from_db()

        out = TripSerializer(trip)
        return standard_response(
            data=out.data,
            message="Trip created and initial ETA calculated successfully.",
            status_code=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        serializer = TripSerializer(self.get_queryset(), many=True)
        return standard_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = TripSerializer(instance)
        return standard_response(data=serializer.data)

    @action(detail=True, methods=['post'], url_path='start')
    def start_trip(self, request, pk=None):
        trip = self.get_object()
        if trip.status != TripStatus.CREATED:
            return standard_response(
                success=False,
                message=f"Cannot start trip with status '{trip.status}'.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        trip.status = TripStatus.ON_ROUTE
        trip.start_time = timezone.now()
        trip.save(update_fields=['status', 'start_time', 'updated_at'])
        return standard_response(
            data=TripSerializer(trip).data,
            message="Trip started and status updated to on_route.",
        )

    @action(detail=True, methods=['post'], url_path='complete')
    def complete_trip(self, request, pk=None):
        trip = self.get_object()
        trip.status = TripStatus.DELIVERED
        trip.end_time = timezone.now()
        trip.save(update_fields=['status', 'end_time', 'updated_at'])
        return standard_response(
            data=TripSerializer(trip).data,
            message="Trip completed and marked as delivered.",
        )

    @action(detail=True, methods=['post'], url_path='recalculate-eta')
    def recalculate_eta(self, request, pk=None):
        trip = self.get_object()
        ETAEstimationService.update_trip_eta(trip)
        trip.refresh_from_db()
        return standard_response(
            data=TripSerializer(trip).data,
            message="Trip ETA and expected delay updated successfully.",
        )
