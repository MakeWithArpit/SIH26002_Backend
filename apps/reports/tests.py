import io
from PIL import Image
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Role
from apps.reports.models import IncidentReport, IncidentType, SeverityLevel, AnalysisStatus


def get_test_image():
    """Generate a tiny valid in-memory JPEG for upload testing."""
    file_obj = io.BytesIO()
    image = Image.new('RGB', (10, 10), color='red')
    image.save(file_obj, format='JPEG')
    file_obj.seek(0)
    return SimpleUploadedFile('test_photo.jpg', file_obj.read(), content_type='image/jpeg')


class IncidentReportAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create Field Officer 1
        self.officer1 = User.objects.create_user(username='officer1', password='Password123!')
        self.officer1.profile.role = Role.FIELD_OFFICER
        self.officer1.profile.save()

        # Create Field Officer 2
        self.officer2 = User.objects.create_user(username='officer2', password='Password123!')
        self.officer2.profile.role = Role.FIELD_OFFICER
        self.officer2.profile.save()

        # Create Normal User
        self.normal_user = User.objects.create_user(username='normal_user', password='Password123!')
        self.normal_user.profile.role = Role.NORMAL_USER
        self.normal_user.profile.save()

        # Create Admin
        self.admin_user = User.objects.create_user(username='admin_user', password='Password123!')
        self.admin_user.profile.role = Role.ADMIN
        self.admin_user.profile.save()

    def test_field_officer_can_submit_report_and_trigger_ai(self):
        self.client.force_authenticate(user=self.officer1)

        payload = {
            'photo': get_test_image(),
            'latitude': 26.1445,
            'longitude': 91.7362,
            'description': 'Severe flooding near bridge approach road.',
            'incident_type': IncidentType.FLOOD,
            'severity': SeverityLevel.HIGH,
            'client_timestamp': timezone.now().isoformat(),
        }

        response = self.client.post('/api/v1/reports/incidents/', payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        res_data = response.json()
        self.assertTrue(res_data['success'])
        data = res_data['data']

        # Verify output fields
        self.assertEqual(data['incident_type'], IncidentType.FLOOD)
        self.assertEqual(data['severity'], SeverityLevel.HIGH)
        self.assertAlmostEqual(data['latitude'], 26.1445, places=4)
        self.assertAlmostEqual(data['longitude'], 91.7362, places=4)
        self.assertEqual(data['officer_username'], 'officer1')

        # Verify AI photo analysis stub executed and persisted
        self.assertEqual(data['analysis_status'], AnalysisStatus.COMPLETED)
        self.assertEqual(data['ai_issue_type'], 'flood')
        self.assertEqual(data['ai_severity'], 'high')
        self.assertGreater(data['ai_confidence'], 0.0)

        # Verify database record
        report = IncidentReport.objects.get(pk=data['id'])
        self.assertEqual(report.officer, self.officer1)
        self.assertAlmostEqual(report.location.y, 26.1445, places=4)
        self.assertAlmostEqual(report.location.x, 91.7362, places=4)

    def test_normal_user_cannot_submit_report(self):
        self.client.force_authenticate(user=self.normal_user)
        payload = {
            'photo': get_test_image(),
            'latitude': 26.1445,
            'longitude': 91.7362,
            'description': 'Normal user trying to submit.',
            'incident_type': IncidentType.ROAD_DAMAGE,
            'severity': SeverityLevel.LOW,
            'client_timestamp': timezone.now().isoformat(),
        }
        response = self.client.post('/api/v1/reports/incidents/', payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_rejected(self):
        response = self.client.get('/api/v1/reports/incidents/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_scoping_officer_sees_only_own_reports_admin_sees_all(self):
        # Officer 1 submits report
        self.client.force_authenticate(user=self.officer1)
        payload1 = {
            'photo': get_test_image(),
            'latitude': 26.1445,
            'longitude': 91.7362,
            'description': 'Report by officer 1',
            'incident_type': IncidentType.FLOOD,
            'severity': SeverityLevel.HIGH,
            'client_timestamp': timezone.now().isoformat(),
        }
        res1 = self.client.post('/api/v1/reports/incidents/', payload1, format='multipart')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Officer 2 submits report
        self.client.force_authenticate(user=self.officer2)
        payload2 = {
            'photo': get_test_image(),
            'latitude': 25.5788,
            'longitude': 91.8933,
            'description': 'Report by officer 2',
            'incident_type': IncidentType.LANDSLIDE,
            'severity': SeverityLevel.MEDIUM,
            'client_timestamp': timezone.now().isoformat(),
        }
        res2 = self.client.post('/api/v1/reports/incidents/', payload2, format='multipart')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # Officer 1 lists reports -> should see only 1
        self.client.force_authenticate(user=self.officer1)
        list_res1 = self.client.get('/api/v1/reports/incidents/')
        self.assertEqual(list_res1.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res1.json()['data']), 1)
        self.assertEqual(list_res1.json()['data'][0]['description'], 'Report by officer 1')

        # Admin lists reports -> should see all 2
        self.client.force_authenticate(user=self.admin_user)
        admin_list = self.client.get('/api/v1/reports/incidents/')
        self.assertEqual(admin_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(admin_list.json()['data']), 2)

    def test_validation_missing_photo_returns_standard_error(self):
        self.client.force_authenticate(user=self.officer1)
        payload = {
            'latitude': 26.1445,
            'longitude': 91.7362,
            'description': 'Missing photo report',
            'incident_type': IncidentType.OBSTRUCTION,
            'severity': SeverityLevel.LOW,
            'client_timestamp': timezone.now().isoformat(),
        }
        response = self.client.post('/api/v1/reports/incidents/', payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error']['code'], 'INVALID_REQUEST')
        self.assertIn('photo', data['error']['details'])
