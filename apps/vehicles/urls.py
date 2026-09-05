from rest_framework.routers import DefaultRouter
from .views import VehicleViewSet, TripViewSet

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'trips', TripViewSet, basename='trip')

urlpatterns = router.urls
