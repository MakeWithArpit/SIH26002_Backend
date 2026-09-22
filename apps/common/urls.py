from django.urls import path
from apps.common.views import HealthCheckView, APIRootView

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('root/', APIRootView.as_view(), name='api-root-v1'),
]
