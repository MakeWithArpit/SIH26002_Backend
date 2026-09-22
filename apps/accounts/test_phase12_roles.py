"""
Phase 12 — Production Hardening & User Role Management: Test Suite

Tests:
  1. assign_user_roles command auto-syncs roles based on username conventions.
  2. assign_user_roles command updates a specific user's role and staff status.
  3. GET /api/v1/accounts/users/ — Admin can list users.
  4. GET /api/v1/accounts/users/?role=field_officer — Admin can filter by role.
  5. GET /api/v1/accounts/users/ — Non-admin is forbidden (403).
  6. PATCH /api/v1/accounts/users/<id>/role/ — Admin can update user role.
  7. PATCH /api/v1/accounts/users/<id>/role/ — Non-admin cannot update user role (403).
  8. POST /api/v1/accounts/sync-roles/ — Admin can trigger bulk role synchronization.
  9. GET / (Root API view) — Returns 200 OK and valid JSON platform directory.
 10. GET /api/v1/health/ — Returns 200 OK and healthy status.
"""
from io import StringIO
from django.core.management import call_command
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Profile, Role


class Phase12RoleManagementTests(APITestCase):

    def setUp(self):
        # Admin user
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='Password123!',
            email='admin@test.com',
            is_staff=True,
        )
        self.admin_user.profile.role = Role.ADMIN
        self.admin_user.profile.save()
        self.admin_user.refresh_from_db()

        # Field Officer user
        self.fo_user = User.objects.create_user(
            username='fo_test',
            password='Password123!',
            email='fo@test.com',
        )
        self.fo_user.profile.role = Role.FIELD_OFFICER
        self.fo_user.profile.save()
        self.fo_user.refresh_from_db()

        # Normal User / Driver
        self.driver_user = User.objects.create_user(
            username='driver_test',
            password='Password123!',
            email='driver@test.com',
        )
        self.driver_user.profile.role = Role.NORMAL_USER
        self.driver_user.profile.save()
        self.driver_user.refresh_from_db()

    # -------------------------------------------------------------------------
    # Management Command Tests
    # -------------------------------------------------------------------------

    def test_assign_user_roles_command_auto_sync(self):
        """Auto-sync sets role=admin and is_staff=True on admin_* users."""
        new_admin = User.objects.create_user(username='admin_new', password='pwd')
        # profile defaults to normal_user
        profile, _ = Profile.objects.get_or_create(user=new_admin)
        profile.role = Role.NORMAL_USER
        profile.save()

        out = StringIO()
        call_command('assign_user_roles', stdout=out)

        new_admin.refresh_from_db()
        new_admin.profile.refresh_from_db()
        self.assertEqual(new_admin.profile.role, Role.ADMIN)
        self.assertTrue(new_admin.is_staff)

    def test_assign_user_roles_command_specific_user(self):
        """Explicitly assigning a role and staff flag via command."""
        test_user = User.objects.create_user(username='custom_user', password='pwd')

        out = StringIO()
        call_command('assign_user_roles', username='custom_user', role='field_officer', staff=True, stdout=out)

        test_user.refresh_from_db()
        self.assertEqual(test_user.profile.role, Role.FIELD_OFFICER)
        self.assertTrue(test_user.is_staff)

    # -------------------------------------------------------------------------
    # Role API Tests
    # -------------------------------------------------------------------------

    def test_admin_can_list_users(self):
        """Admin can retrieve list of all users."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/v1/accounts/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertGreaterEqual(len(response.data['data']), 3)

    def test_admin_can_filter_users_by_role(self):
        """Admin can filter user list by role."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/v1/accounts/users/?role=field_officer')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for user_data in response.data['data']:
            self.assertEqual(user_data['profile']['role'], Role.FIELD_OFFICER)

    def test_non_admin_cannot_list_users(self):
        """Normal user and Field Officer get 403 Forbidden on user list."""
        self.client.force_authenticate(user=self.fo_user)
        response = self.client.get('/api/v1/accounts/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get('/api/v1/accounts/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_update_user_role(self):
        """Admin can promote a driver to field_officer via PATCH."""
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'role': Role.FIELD_OFFICER,
            'department': 'Assam Quick Response',
        }
        response = self.client.patch(f'/api/v1/accounts/users/{self.driver_user.id}/role/', payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.driver_user.refresh_from_db()
        self.assertEqual(self.driver_user.profile.role, Role.FIELD_OFFICER)
        self.assertEqual(self.driver_user.profile.department, 'Assam Quick Response')

    def test_non_admin_cannot_update_user_role(self):
        """Field officer attempting to update a role gets 403 Forbidden."""
        self.client.force_authenticate(user=self.fo_user)
        payload = {'role': Role.ADMIN}
        response = self.client.patch(f'/api/v1/accounts/users/{self.driver_user.id}/role/', payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_bulk_sync_roles_api(self):
        """Admin can trigger bulk auto-synchronization endpoint."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/v1/accounts/sync-roles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_users', response.data['data'])

    # -------------------------------------------------------------------------
    # Root & Health Check Tests (Phase 12 Production Hardening)
    # -------------------------------------------------------------------------

    def test_root_api_view_returns_operational(self):
        """GET / returns 200 with service information and endpoint map."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['status'], 'operational')
        self.assertIn('documentation', data)
        self.assertIn('endpoints_v1', data)
        self.assertIn('admin', data)

    def test_health_check_returns_healthy(self):
        """GET /api/v1/health/ returns 200 with database connectivity healthy."""
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['status'], 'healthy')
        self.assertEqual(data['database'], 'healthy')
        self.assertIn('Phase 12', data['phase'])
