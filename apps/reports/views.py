from rest_framework import viewsets, status
from rest_framework.parsers import MultiPartParser, FormParser

from apps.accounts.permissions import IsFieldOfficer, IsAdminRole
from apps.common.responses import standard_response
from .models import IncidentReport
from .serializers import IncidentReportCreateSerializer, IncidentReportSerializer
from .services import photo_analysis, spatial_snap


class IncidentReportViewSet(viewsets.ModelViewSet):
    """
    ViewSet for field incident reports.

    - Field Officers can create reports and list/retrieve their own.
    - Admins can list/retrieve all reports.
    - No update/delete — reports are immutable once submitted.
    """
    permission_classes = [IsFieldOfficer]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return IncidentReportCreateSerializer
        return IncidentReportSerializer

    def get_queryset(self):
        user = self.request.user
        qs = IncidentReport.objects.select_related('officer')

        # Admins see all; field officers see only their own
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin_role):
            return qs
        return qs.filter(officer=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Run the photo analysis CV pipeline (stub in Phase 1)
        photo_analysis.analyse(report)

        # Snap to nearest road segment (stub until Phase 2)
        spatial_snap.snap(report)

        # Refresh from DB to pick up service-updated fields
        report.refresh_from_db()

        out = IncidentReportSerializer(report, context={'request': request})
        return standard_response(
            data=out.data,
            message='Incident report submitted successfully.',
            status_code=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return standard_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return standard_response(data=serializer.data)
