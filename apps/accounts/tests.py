from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import Profile, Role

class Phase0FoundationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_check_endpoint(self):
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['status'], 'healthy')
        self.assertEqual(data['data']['phase'], 'Phase 0 - Foundation')

    def test_user_registration_and_profile_signal(self):
        payload = {
            "username": "officer_test",
            "email": "officer@sih.gov.in",
            "password": "SecurePassword123!",
            "role": "field_officer",
            "phone": "+919876543210",
            "department": "PWD Assam"
        }
        response = self.client.post('/api/v1/auth/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertEqual(res_data['data']['username'], 'officer_test')
        self.assertEqual(res_data['data']['profile']['role'], 'field_officer')

        # Verify DB state
        user = User.objects.get(username='officer_test')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertEqual(user.profile.role, Role.FIELD_OFFICER)

    def test_jwt_login_flow(self):
        # Register user
        User.objects.create_user(username='login_test', password='TestPassword123')
        
        # Authenticate
        login_response = self.client.post('/api/v1/auth/login/', {
            'username': 'login_test',
            'password': 'TestPassword123'
        }, format='json')
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        tokens = login_response.json()
        self.assertIn('access', tokens)
        self.assertIn('refresh', tokens)

        # Access protected endpoint with Bearer token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        me_response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        me_data = me_response.json()
        self.assertTrue(me_data['success'])
        self.assertEqual(me_data['data']['username'], 'login_test')

    def test_standardized_error_envelope(self):
        # Trigger validation error on registration (missing password)
        response = self.client.post('/api/v1/auth/register/', {'username': 'incomplete'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        err_data = response.json()
        self.assertFalse(err_data['success'])
        self.assertIn('error', err_data)
        self.assertEqual(err_data['error']['code'], 'INVALID_REQUEST')
        self.assertIn('password', err_data['error']['details'])
