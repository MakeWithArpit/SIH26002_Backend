"""
Phase 6 Weather Intelligence Tests

Tests for:
- Weather service integration
- Celery task execution
- Weather-to-risk pipeline
- API endpoints
- Alert generation
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from datetime import datetime

from apps.routes.models import District, Infrastructure, WeatherSnapshot
from apps.routes.services.weather.service import WeatherService
from apps.routes.services.weather.base import WeatherData
from apps.routes.services.alerts import WeatherAlertService
from apps.routes.tasks import sync_weather_task, sync_weather_and_update_risk_task


class WeatherServiceTest(TestCase):
    """Test weather synchronization service."""
    
    def setUp(self):
        self.district = District.objects.create(
            name='Test District',
            state='Assam',
            geom='SRID=4326;MULTIPOLYGON(((91.7 26.1, 91.8 26.1, 91.8 26.2, 91.7 26.2, 91.7 26.1)))'
        )
    
    @patch('apps.routes.services.weather.service.WeatherService.get_provider')
    def test_sync_district_success(self, mock_get_provider):
        """Test successful weather sync for a single district."""
        mock_provider = MagicMock()
        mock_provider.fetch_weather.return_value = WeatherData(
            rainfall_mm=45.0,
            condition='moderate',
            temperature_c=28.5,
            humidity_pct=75.0,
            wind_speed_kmh=12.0,
            weather_warning=False,
            warning_details='',
            recorded_at=timezone.now(),
            raw_payload={},
        )
        mock_get_provider.return_value = mock_provider
        
        snapshot = WeatherService.sync_district(self.district)
        
        self.assertIsNotNone(snapshot.id)
        self.assertEqual(snapshot.district, self.district)
        self.assertEqual(snapshot.rainfall_mm, 45.0)
        self.assertEqual(snapshot.condition, 'moderate')
        self.assertEqual(snapshot.temperature_c, 28.5)
    
    @patch('apps.routes.services.weather.service.WeatherService.get_provider')
    def test_sync_all_districts_with_failure_isolation(self, mock_get_provider):
        """Test that one district failure doesn't stop others from syncing."""
        district2 = District.objects.create(
            name='Test District 2',
            state='Assam',
            geom='SRID=4326;MULTIPOLYGON(((92.0 26.1, 92.1 26.1, 92.1 26.2, 92.0 26.2, 92.0 26.1)))'
        )
        
        mock_provider = MagicMock()
        
        def fetch_weather_side_effect(lat, lng):
            if lat == 26.15:  # First district
                raise Exception("API Error")
            return WeatherData(
                rainfall_mm=30.0,
                condition='clear',
                temperature_c=25.0,
                humidity_pct=60.0,
                wind_speed_kmh=8.0,
                weather_warning=False,
                warning_details='',
                recorded_at=timezone.now(),
                raw_payload={},
            )
        
        mock_provider.fetch_weather.side_effect = fetch_weather_side_effect
        mock_get_provider.return_value = mock_provider
        
        result = WeatherService.sync_all_districts()
        
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['failed_count'], 1)
        self.assertEqual(result['successful_count'], 1)


class WeatherToRiskIntegrationTest(TestCase):
    """Test weather data propagation to infrastructure risk scores."""
    
    def setUp(self):
        self.district = District.objects.create(
            name='Test District',
            state='Assam',
            geom='SRID=4326;MULTIPOLYGON(((91.7 26.1, 91.8 26.1, 91.8 26.2, 91.7 26.2, 91.7 26.1)))'
        )
        
        self.infrastructure = Infrastructure.objects.create(
            name='Test Road',
            district=self.district,
            infra_type='road',
            road_classification='national_highway',
            geom='SRID=4326;LINESTRING(91.75 26.15, 91.77 26.17)',
            length_km=5.0,
            base_speed_kmh=50.0,
            landslide_susceptibility='high',
            flood_hazard_zone='low',
            historical_landslide_count=0,
            recent_rainfall_mm=0.0,
            weather_warning=False,
        )
    
    @patch('apps.routes.services.weather.service.WeatherService.get_provider')
    def test_weather_sync_updates_infrastructure_risk(self, mock_get_provider):
        """Test that weather sync triggers risk recalculation."""
        mock_provider = MagicMock()
        mock_provider.fetch_weather.return_value = WeatherData(
            rainfall_mm=65.0,  # Heavy rainfall
            condition='heavy',
            temperature_c=28.0,
            humidity_pct=85.0,
            wind_speed_kmh=15.0,
            weather_warning=True,
            warning_details='Heavy rain warning',
            recorded_at=timezone.now(),
            raw_payload={},
        )
        mock_get_provider.return_value = mock_provider
        
        initial_risk = self.infrastructure.risk_score
        
        # Sync weather
        WeatherService.sync_district(self.district)
        
        # Manually propagate to infrastructure (simulating the task)
        self.infrastructure.refresh_from_db()
        snapshot = self.district.latest_weather
        
        self.infrastructure.recent_rainfall_mm = snapshot.rainfall_mm
        self.infrastructure.weather_warning = snapshot.weather_warning
        
        from apps.routes.services.risk import RiskPredictionService
        risk_result = RiskPredictionService.calculate_risk(self.infrastructure)
        
        self.infrastructure.risk_score = risk_result['risk_score']
        self.infrastructure.risk_level = risk_result['risk_level']
        self.infrastructure.save()
        
        # Verify risk increased due to weather
        self.assertGreater(self.infrastructure.risk_score, initial_risk)
        self.assertEqual(self.infrastructure.risk_level, 'high')


class WeatherAlertServiceTest(TestCase):
    """Test weather-based alert generation."""
    
    def setUp(self):
        self.district = District.objects.create(
            name='Test District',
            state='Assam',
            geom='SRID=4326;MULTIPOLYGON(((91.7 26.1, 91.8 26.1, 91.8 26.2, 91.7 26.2, 91.7 26.1)))'
        )
        
        WeatherSnapshot.objects.create(
            district=self.district,
            rainfall_mm=120.0,  # Extreme rainfall
            condition='extreme',
            temperature_c=27.0,
            humidity_pct=90.0,
            wind_speed_kmh=20.0,
            weather_warning=True,
            warning_details='Extreme rainfall warning',
            recorded_at=timezone.now(),
        )
    
    def test_generate_weather_alerts_for_extreme_rainfall(self):
        """Test that extreme rainfall generates critical alerts."""
        alerts = WeatherAlertService.generate_weather_alerts()
        
        self.assertGreater(len(alerts), 0)
        
        extreme_alert = next((a for a in alerts if a['type'] == 'extreme_weather'), None)
        self.assertIsNotNone(extreme_alert)
        self.assertEqual(extreme_alert['severity'], 'critical')
        self.assertEqual(extreme_alert['district_id'], self.district.id)
    
    def test_generate_infrastructure_alert(self):
        """Test infrastructure alert generation."""
        infra = Infrastructure.objects.create(
            name='High Risk Road',
            district=self.district,
            infra_type='road',
            road_classification='national_highway',
            geom='SRID=4326;LINESTRING(91.75 26.15, 91.77 26.17)',
            length_km=5.0,
            base_speed_kmh=50.0,
            risk_score=85.0,
            risk_level='high',
            disruption_probability=0.85,
            top_factors=['heavy rainfall', 'high landslide susceptibility'],
        )
        
        result = WeatherAlertService.generate_all_alerts()
        
        self.assertGreater(result['total_alerts'], 0)
        self.assertIn('severity_breakdown', result)


class WeatherAPIEndpointTest(TestCase):
    """Test Phase 6 weather API endpoints."""
    
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        
        self.district = District.objects.create(
            name='Test District',
            state='Assam',
            geom='SRID=4326;MULTIPOLYGON(((91.7 26.1, 91.8 26.1, 91.8 26.2, 91.7 26.2, 91.7 26.1)))'
        )
        
        WeatherSnapshot.objects.create(
            district=self.district,
            rainfall_mm=45.0,
            condition='moderate',
            temperature_c=28.0,
            humidity_pct=75.0,
            wind_speed_kmh=12.0,
            weather_warning=False,
            recorded_at=timezone.now(),
        )
    
    def test_get_latest_weather_endpoint(self):
        """Test GET /api/v1/routes/weather/latest/"""
        from rest_framework.test import APIClient
        
        client = APIClient()
        client.force_authenticate(user=self.user)
        
        response = client.get('/api/v1/routes/weather/latest/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['count'], 1)
    
    def test_get_district_weather_history_endpoint(self):
        """Test GET /api/v1/routes/weather/districts/{id}/history/"""
        from rest_framework.test import APIClient
        
        client = APIClient()
        client.force_authenticate(user=self.user)
        
        response = client.get(f'/api/v1/routes/weather/districts/{self.district.id}/history/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['district_id'], self.district.id)
        self.assertGreater(len(data['data']['snapshots']), 0)


@pytest.mark.django_db
class TestCeleryTasks:
    """Test Celery tasks for Phase 6."""
    
    @patch('apps.routes.tasks.WeatherService.sync_all_districts')
    def test_sync_weather_task(self, mock_sync):
        """Test weather sync Celery task."""
        mock_sync.return_value = {
            'total': 2,
            'successful_count': 2,
            'failed_count': 0,
        }
        
        result = sync_weather_task()
        
        assert result['status'] == 'completed'
        assert result['successful_count'] == 2
        mock_sync.assert_called_once()
