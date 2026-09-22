"""
Test suite: Registration Validation (Phase A) + Field Officer Approval Flow (Phase B)

Phase A tests:
  - Duplicate username → error + suggestions
  - Duplicate email → error
  - Duplicate phone → error
  - Admin role blocked from public registration

Phase B tests:
  - Field Officer registers as PENDING
  - Driver registers as APPROVED
  - PENDING FO cannot log in (403)
  - REJECTED FO cannot log in (403)
  - Admin approves FO → FO can log in
  - Admin rejects FO → FO cannot log in
  - Non-FO cannot use approve endpoint
"""
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.accounts.models import Profile, Role, ApprovalStatus


class RegistrationValidationTests(APITestCase):
    """Phase A: input validation and username suggestions."""

    def setUp(self):
        self.url = reverse('auth-register')
        self.base_payload = {
            'username': 'existing_user',
            'email': 'existing@example.com',
            'password': 'TestPass123',
            'phone': '9000000001',
            'role': 'normal_user',
        }
        # Create an existing user to trigger duplicate checks
        user = User.objects.create_user(
            username='existing_user',
            email='existing@example.com',
            password='TestPass123',
        )
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.phone = '9000000001'
        profile.save()

    def _get_errors(self, res):
        if isinstance(res.data, dict) and 'error' in res.data:
            return res.data['error'].get('details', {})
        return res.data.get('errors', res.data)

    def test_duplicate_username_returns_error_and_suggestions(self):
        res = self.client.post(self.url, self.base_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        errors = self._get_errors(res)
        username_error = errors.get('username', [])
        # Error should contain message and suggestions
        self.assertTrue(len(username_error) > 0)
        self.assertIn('suggestions', str(username_error))

    def test_duplicate_email_returns_clear_error(self):
        payload = {**self.base_payload, 'username': 'new_unique_user'}
        res = self.client.post(self.url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        errors = self._get_errors(res)
        self.assertIn('email', errors)

    def test_duplicate_phone_returns_error(self):
        payload = {**self.base_payload, 'username': 'another_user', 'email': 'fresh@example.com'}
        res = self.client.post(self.url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        errors = self._get_errors(res)
        self.assertIn('phone', errors)

    def test_admin_role_blocked_from_public_registration(self):
        payload = {
            'username': 'hacker_admin',
            'email': 'hacker@example.com',
            'password': 'TestPass123',
            'role': 'admin',
        }
        res = self.client.post(self.url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        errors = self._get_errors(res)
        self.assertIn('role', errors)

    def test_driver_registration_succeeds_as_approved(self):
        payload = {
            'username': 'driver_new',
            'email': 'drivernew@example.com',
            'password': 'TestPass123',
            'role': 'normal_user',
        }
        res = self.client.post(self.url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='driver_new')
        self.assertEqual(user.profile.approval_status, ApprovalStatus.APPROVED)


class FieldOfficerApprovalFlowTests(APITestCase):
    """Phase B: FO pending/approve/reject lifecycle."""

    def setUp(self):
        self.register_url = reverse('auth-register')
        self.login_url = reverse('token_obtain_pair')

        # Create admin user
        self.admin_user = User.objects.create_user(
            username='admin_test', password='AdminPass123', email='admin@test.com'
        )
        self.admin_user.is_staff = True
        self.admin_user.is_superuser = True
        self.admin_user.save()
        profile, _ = Profile.objects.get_or_create(user=self.admin_user)
        profile.role = Role.ADMIN
        profile.approval_status = ApprovalStatus.APPROVED
        profile.save()

    def _register_fo(self, username='fo_testuser', email='fo@test.com'):
        payload = {
            'username': username,
            'email': email,
            'password': 'FoPass123',
            'role': 'field_officer',
        }
        return self.client.post(self.register_url, payload, format='json')

    def test_fo_registers_as_pending(self):
        res = self._register_fo()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='fo_testuser')
        self.assertEqual(user.profile.approval_status, ApprovalStatus.PENDING)
        self.assertIn('pending', res.data.get('message', '').lower())

    def test_pending_fo_cannot_login(self):
        self._register_fo()
        res = self.client.post(self.login_url, {'username': 'fo_testuser', 'password': 'FoPass123'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        response_str = str(res.data).lower()
        self.assertIn('pending', response_str)

    def test_admin_approves_fo_and_fo_can_login(self):
        self._register_fo()
        fo_user = User.objects.get(username='fo_testuser')

        # Admin approves
        self.client.force_authenticate(user=self.admin_user)
        approve_url = reverse('user-approve', kwargs={'user_id': fo_user.id})
        res = self.client.patch(approve_url, {'action': 'approve'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # FO should now be able to log in
        self.client.force_authenticate(user=None)
        login_res = self.client.post(self.login_url, {'username': 'fo_testuser', 'password': 'FoPass123'}, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

    def test_admin_rejects_fo_and_fo_cannot_login(self):
        self._register_fo(username='fo_rejected', email='forej@test.com')
        fo_user = User.objects.get(username='fo_rejected')

        # Admin rejects
        self.client.force_authenticate(user=self.admin_user)
        approve_url = reverse('user-approve', kwargs={'user_id': fo_user.id})
        res = self.client.patch(approve_url, {'action': 'reject'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # FO should be blocked at login
        self.client.force_authenticate(user=None)
        login_res = self.client.post(self.login_url, {'username': 'fo_rejected', 'password': 'FoPass123'}, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rejected', str(login_res.data).lower())

    def test_approve_invalid_action_returns_400(self):
        self._register_fo()
        fo_user = User.objects.get(username='fo_testuser')
        self.client.force_authenticate(user=self.admin_user)
        approve_url = reverse('user-approve', kwargs={'user_id': fo_user.id})
        res = self.client.patch(approve_url, {'action': 'promote'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_non_fo_user_returns_400(self):
        # Try to approve a driver
        driver = User.objects.create_user(username='driver_xyz', password='Pass123', email='drv@test.com')
        profile, _ = Profile.objects.get_or_create(user=driver)
        profile.role = Role.NORMAL_USER
        profile.approval_status = ApprovalStatus.APPROVED
        profile.save()

        self.client.force_authenticate(user=self.admin_user)
        approve_url = reverse('user-approve', kwargs={'user_id': driver.id})
        res = self.client.patch(approve_url, {'action': 'approve'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pending_users_filter_works(self):
        self._register_fo()
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get('/api/v1/accounts/users/?approval_status=pending')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        usernames = [u['username'] for u in res.data.get('data', [])]
        self.assertIn('fo_testuser', usernames)
