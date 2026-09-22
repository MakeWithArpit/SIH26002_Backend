"""
Test Suite: Rate Limiting & Brute-Force Protection
Tests:
  1. Login endpoint throttles after 5 attempts per minute (returns HTTP 429).
  2. Throttled response contains standardized envelope: code='TOO_MANY_REQUESTS' and retry_after_seconds.
  3. Register endpoint throttles after 3 attempts per minute (returns HTTP 429).
"""
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class RateLimitingTests(APITestCase):

    def setUp(self):
        cache.clear()
        self.login_url = reverse('token_obtain_pair')
        self.register_url = reverse('auth-register')

    def tearDown(self):
        cache.clear()

    def test_login_rate_limiting_after_5_attempts(self):
        """
        Verify /login/ permits 5 attempts, then the 6th attempt is throttled with 429.
        """
        for i in range(5):
            res = self.client.post(
                self.login_url,
                {'username': f'test_user_{i}', 'password': 'WrongPassword123'},
                format='json'
            )
            self.assertNotEqual(
                res.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Attempt {i+1} was unexpectedly throttled"
            )

        # 6th attempt MUST be throttled
        throttled_res = self.client.post(
            self.login_url,
            {'username': 'test_user_6', 'password': 'WrongPassword123'},
            format='json'
        )
        self.assertEqual(throttled_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(throttled_res.data.get('success', True))
        error = throttled_res.data.get('error', {})
        self.assertEqual(error.get('code'), 'TOO_MANY_REQUESTS')
        self.assertIn('retry_after_seconds', error.get('details', {}))
        self.assertGreater(error['details']['retry_after_seconds'], 0)

    def test_register_rate_limiting_after_3_attempts(self):
        """
        Verify /register/ permits 3 attempts, then the 4th attempt is throttled with 429.
        """
        for i in range(3):
            res = self.client.post(
                self.register_url,
                {
                    'username': f'newuser_rate_{i}',
                    'email': f'newuser_rate_{i}@example.com',
                    'password': 'PassWord123!',
                    'role': 'normal_user',
                },
                format='json'
            )
            self.assertNotEqual(
                res.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Register attempt {i+1} was unexpectedly throttled"
            )

        # 4th attempt MUST be throttled
        throttled_res = self.client.post(
            self.register_url,
            {
                'username': 'newuser_rate_4',
                'email': 'newuser_rate_4@example.com',
                'password': 'PassWord123!',
                'role': 'normal_user',
            },
            format='json'
        )
        self.assertEqual(throttled_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(throttled_res.data.get('success', True))
        error = throttled_res.data.get('error', {})
        self.assertEqual(error.get('code'), 'TOO_MANY_REQUESTS')
        self.assertIn('retry_after_seconds', error.get('details', {}))
        self.assertGreater(error['details']['retry_after_seconds'], 0)
