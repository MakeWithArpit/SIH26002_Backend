from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import IncidentReportViewSet

router = DefaultRouter()
router.register('incidents', IncidentReportViewSet, basename='incident-report')

urlpatterns = [
    path('', include(router.urls)),
]
