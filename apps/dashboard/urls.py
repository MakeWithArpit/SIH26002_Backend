from django.urls import path
from .views import (
    DashboardSummaryView,
    DashboardDistrictsView,
    DashboardVehiclesView,
    DashboardActiveAlertsView,
    DashboardBottlenecksView,
    DashboardFieldIntelligenceView,
)

urlpatterns = [
    path('summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('districts/', DashboardDistrictsView.as_view(), name='dashboard-districts'),
    path('vehicles/', DashboardVehiclesView.as_view(), name='dashboard-vehicles'),
    path('alerts/active/', DashboardActiveAlertsView.as_view(), name='dashboard-active-alerts'),
    path('bottlenecks/', DashboardBottlenecksView.as_view(), name='dashboard-bottlenecks'),
    path('field-intelligence/', DashboardFieldIntelligenceView.as_view(), name='dashboard-field-intelligence'),
]
