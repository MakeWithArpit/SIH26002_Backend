from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance

from apps.accounts.permissions import IsAdminRole
from apps.common.responses import standard_response
from .models import District, Infrastructure
from .serializers import (
    DistrictSerializer,
    InfrastructureSerializer,
    InfrastructureRiskAssessSerializer,
)
from .services.risk import RiskPredictionService


class DistrictViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for districts and their regional accessibility metrics.
    """
    queryset = District.objects.prefetch_related('infrastructure').all()
    serializer_class = DistrictSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return standard_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return standard_response(data=serializer.data)


class InfrastructureViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Road Segments / Infrastructure.
    - All authenticated users can list and retrieve.
    - Proximity queries supported: ?lat=...&lng=...&radius_m=...
    - Only Admins can manually create/edit/delete infrastructure.
    - Custom action: /assess-risk/ triggers rule-based / ML risk assessment.
    """
    serializer_class = InfrastructureSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminRole()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = Infrastructure.objects.select_related('district').all()

        # Query parameter filters
        district_id = self.request.query_params.get('district')
        if district_id:
            qs = qs.filter(district_id=district_id)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        risk_level = self.request.query_params.get('risk_level')
        if risk_level:
            qs = qs.filter(risk_level=risk_level)

        infra_type = self.request.query_params.get('infra_type')
        if infra_type:
            qs = qs.filter(infra_type=infra_type)

        # Proximity spatial filter: lat, lng, radius_m (default 1000m)
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        if lat and lng:
            try:
                point = Point(float(lng), float(lat), srid=4326)
                radius = float(self.request.query_params.get('radius_m', 1000))
                qs = qs.filter(geom__dwithin=(point, D(m=radius))).annotate(
                    distance=Distance('geom', point)
                ).order_by('distance')
            except (ValueError, TypeError):
                pass

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return standard_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return standard_response(data=serializer.data)

    @action(detail=True, methods=['post'], url_path='assess-risk')
    def assess_risk(self, request, pk=None):
        """
        Recalculates disruption risk on this road segment.
        Accepts optional overrides in payload (recent_rainfall_mm, weather_warning, simulate_only).
        """
        infra = self.get_object()
        req_serializer = InfrastructureRiskAssessSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        validated = req_serializer.validated_data

        # Apply temporary overrides if provided
        if 'recent_rainfall_mm' in validated:
            infra.recent_rainfall_mm = validated['recent_rainfall_mm']
        if 'weather_warning' in validated:
            infra.weather_warning = validated['weather_warning']

        if validated.get('simulate_only', False):
            result = RiskPredictionService.calculate_risk(infra)
            return standard_response(
                data=result,
                message='Simulated risk assessment completed.',
            )

        updated_infra = RiskPredictionService.assess_and_update(infra)
        serializer = self.get_serializer(updated_infra)
        return standard_response(
            data=serializer.data,
            message='Disruption risk assessed and updated successfully.',
        )


class CalculateRouteView(viewsets.views.APIView):
    """
    Phase 3: Route Calculation & Risk-Aware Optimization Endpoint.
    POST /api/v1/routes/calculate/
    Generates candidate routes (shortest vs safest) using NetworkX on PostGIS road graph,
    weighs disruption risk penalties, and provides ranked recommendations.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        from .serializers import RouteCalculationRequestSerializer, RouteCandidateSerializer
        from .services.routing.graph import RoadNetworkGraphService
        from .services.route_ranking import RouteRankingService

        serializer = RouteCalculationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Determine origin node
        origin_node = data.get('origin_node')
        if not origin_node:
            origin_node = RoadNetworkGraphService.find_nearest_node(
                data['origin_lat'], data['origin_lng']
            )

        # Determine destination node
        dest_node = data.get('destination_node')
        if not dest_node:
            dest_node = RoadNetworkGraphService.find_nearest_node(
                data['destination_lat'], data['destination_lng']
            )

        if not origin_node or not dest_node:
            return standard_response(
                success=False,
                message="Could not resolve origin or destination to road network nodes.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            candidates = RoadNetworkGraphService.generate_candidate_routes(origin_node, dest_node)
            ranked_routes = RouteRankingService.rank_routes(candidates)
            serialized_routes = [c.to_dict() for c in ranked_routes]

            return standard_response(
                data={
                    'origin_node': origin_node,
                    'destination_node': dest_node,
                    'routes_count': len(serialized_routes),
                    'routes': serialized_routes,
                },
                message="Candidate routes calculated and ranked successfully.",
            )
        except ValueError as e:
            return standard_response(
                success=False,
                message=str(e),
                status_code=status.HTTP_400_BAD_REQUEST,
            )


class SimulatePipelineView(viewsets.views.APIView):
    """
    Phase 5: End-to-End Intelligence Pipeline Simulation.
    POST /api/v1/routes/simulate-pipeline/

    Steps:
      1. Accept incident details (type, severity, location)
      2. Create report & spatially snap to nearest road segment
      3. Risk engine recalculates on snapped segment
      4. Road graph rebuilds; routes reranked
      5. Condition-aware ETA estimated on recommended route

    Returns before/after snapshots and recommendation_changed flag.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        from apps.reports.models import IncidentReport, IncidentType, SeverityLevel
        from apps.reports.services.spatial_snap import snap
        from .services.routing.graph import RoadNetworkGraphService
        from .services.route_ranking import RouteRankingService
        from apps.vehicles.services.eta import ETAEstimationService

        incident_lat = request.data.get('incident_lat')
        incident_lng = request.data.get('incident_lng')
        incident_type = request.data.get('incident_type', IncidentType.LANDSLIDE)
        severity = request.data.get('severity', SeverityLevel.HIGH)
        origin_node = request.data.get('origin_node')
        destination_node = request.data.get('destination_node')

        if not all([incident_lat, incident_lng, origin_node, destination_node]):
            return standard_response(
                message="Required: incident_lat, incident_lng, origin_node, destination_node",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            before_candidates = RoadNetworkGraphService.generate_candidate_routes(origin_node, destination_node)
        except ValueError as e:
            return standard_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)

        before_ranked = RouteRankingService.rank_routes(before_candidates)
        before_rec = next((c for c in before_ranked if c.recommended), before_ranked[0] if before_ranked else None)

        report = IncidentReport.objects.create(
            officer=request.user,
            photo="reports/photos/pipeline_sim/placeholder.jpg",
            location=Point(float(incident_lng), float(incident_lat), srid=4326),
            description=f"Pipeline simulation: {incident_type} at ({incident_lat}, {incident_lng})",
            incident_type=incident_type,
            severity=severity,
            client_timestamp=timezone.now(),
            ai_issue_type=incident_type,
            ai_severity=severity,
            ai_confidence=0.92,
        )

        snap(report)
        report.refresh_from_db()

        try:
            after_candidates = RoadNetworkGraphService.generate_candidate_routes(origin_node, destination_node)
        except ValueError as e:
            report.delete()
            return standard_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)

        after_ranked = RouteRankingService.rank_routes(after_candidates)
        after_rec = next((c for c in after_ranked if c.recommended), after_ranked[0] if after_ranked else None)

        eta_result = None
        if after_rec:
            segs = [
                {
                    'length_km': seg['length_km'],
                    'road_classification': 'national_highway',
                    'risk_score': seg['risk_score'],
                    'status': seg['status'],
                }
                for seg in after_rec.segments
            ]
            eta_result = ETAEstimationService.calculate_eta_for_route(segments=segs)

        snapped_name = report.snapped_infrastructure.name if report.snapped_infrastructure else None
        report.delete()

        return standard_response(
            data={
                'pipeline_steps': [
                    'incident_report_created',
                    'spatial_snap_executed',
                    'risk_recalculated',
                    'routes_reranked',
                    'eta_estimated',
                ],
                'incident': {
                    'type': incident_type,
                    'severity': severity,
                    'location': {'lat': incident_lat, 'lng': incident_lng},
                    'snapped_to': snapped_name,
                },
                'before': {
                    'recommended_route': before_rec.route_id if before_rec else None,
                    'recommended_route_name': before_rec.name if before_rec else None,
                    'risk_level': before_rec.risk_level if before_rec else None,
                    'base_eta_minutes': before_rec.base_eta_minutes if before_rec else None,
                },
                'after': {
                    'recommended_route': after_rec.route_id if after_rec else None,
                    'recommended_route_name': after_rec.name if after_rec else None,
                    'risk_level': after_rec.risk_level if after_rec else None,
                    'base_eta_minutes': after_rec.base_eta_minutes if after_rec else None,
                    'routes': [c.to_dict() for c in after_ranked],
                },
                'eta': eta_result,
                'recommendation_changed': (
                    before_rec.route_id != after_rec.route_id
                    if before_rec and after_rec else False
                ),
            },
            message="End-to-end intelligence pipeline simulated successfully.",
        )
