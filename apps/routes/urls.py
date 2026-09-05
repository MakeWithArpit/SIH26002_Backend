from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import DistrictViewSet, InfrastructureViewSet, CalculateRouteView, SimulatePipelineView

router = DefaultRouter()
router.register(r'districts', DistrictViewSet, basename='district')
router.register(r'infrastructure', InfrastructureViewSet, basename='infrastructure')

urlpatterns = [
    path('calculate/', CalculateRouteView.as_view(), name='calculate-route'),
    path('simulate-pipeline/', SimulatePipelineView.as_view(), name='simulate-pipeline'),
] + router.urls

