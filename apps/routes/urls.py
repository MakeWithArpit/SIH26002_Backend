from rest_framework.routers import DefaultRouter
from .views import DistrictViewSet, InfrastructureViewSet

router = DefaultRouter()
router.register(r'districts', DistrictViewSet, basename='district')
router.register(r'infrastructure', InfrastructureViewSet, basename='infrastructure')

urlpatterns = router.urls
