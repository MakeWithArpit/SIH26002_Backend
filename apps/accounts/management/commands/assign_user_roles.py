"""
Management command: assign_user_roles

Assigns and synchronizes user roles (admin, field_officer, normal_user)
and staff permissions across the database.

Usage:
    # Auto-assign roles to all users based on username conventions
    python manage.py assign_user_roles

    # List all users, roles, and staff status
    python manage.py assign_user_roles --list

    # Assign a specific role to a single user
    python manage.py assign_user_roles --username admin_raj --role admin --staff
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.accounts.models import Profile, Role


class Command(BaseCommand):
    help = 'Assign and synchronize user roles (admin, field_officer, normal_user) and staff permissions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all users with their current profile roles and staff status',
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Target specific username to update',
        )
        parser.add_argument(
            '--role',
            type=str,
            choices=[r.value for r in Role],
            help='Role to assign (admin, field_officer, normal_user)',
        )
        parser.add_argument(
            '--staff',
            action='store_true',
            help='Grant is_staff permission (required for /admin/ login)',
        )
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Grant is_superuser permission',
        )

    def handle(self, *args, **options):
        if options['list']:
            self._list_users()
            return

        if options['username']:
            self._update_single_user(options)
            return

        self._auto_sync_all_users()

    def _list_users(self):
        self.stdout.write(self.style.NOTICE('\n=== CURRENT USERS & ROLES ===\n'))
        users = User.objects.all().order_by('username')
        self.stdout.write(f"{'Username':<22} {'Role':<16} {'Staff':<8} {'Super':<8} {'Department':<20}")
        self.stdout.write('-' * 74)

        for u in users:
            profile = getattr(u, 'profile', None)
            role_val = profile.role if profile else 'NO PROFILE'
            dept = profile.department if profile else ''
            self.stdout.write(
                f"{u.username:<22} {role_val:<16} {str(u.is_staff):<8} {str(u.is_superuser):<8} {dept:<20}"
            )
        self.stdout.write(self.style.SUCCESS(f'\nTotal Users: {users.count()}\n'))

    def _update_single_user(self, options):
        username = options['username']
        role_choice = options.get('role')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' does not exist."))
            return

        profile, _ = Profile.objects.get_or_create(user=user)

        if role_choice:
            profile.role = role_choice
            profile.save()
            self.stdout.write(self.style.SUCCESS(f"Updated role for {username} -> {role_choice}"))

        if options.get('staff'):
            user.is_staff = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Granted is_staff to {username}"))

        if options.get('superuser'):
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Granted is_superuser to {username}"))

    def _auto_sync_all_users(self):
        self.stdout.write(self.style.NOTICE('\n=== AUTO-SYNCHRONIZING USER ROLES ===\n'))

        updated_count = 0
        created_profiles = 0

        for user in User.objects.all():
            profile, created = Profile.objects.get_or_create(user=user)
            if created:
                created_profiles += 1

            uname = user.username.lower()
            changed = False

            # Determine role based on username prefix or existing status
            if uname.startswith('admin') or user.is_superuser:
                target_role = Role.ADMIN
                if not user.is_staff:
                    user.is_staff = True
                    user.save(update_fields=['is_staff'])
                    changed = True
            elif uname.startswith('fo_') or uname.startswith('officer'):
                target_role = Role.FIELD_OFFICER
            elif uname.startswith('driver_') or uname.startswith('user_'):
                target_role = Role.NORMAL_USER
            else:
                # Keep existing role if already set, else default to NORMAL_USER
                target_role = profile.role or Role.NORMAL_USER

            if profile.role != target_role:
                profile.role = target_role
                changed = True

            # Populate default departments if empty
            if not profile.department:
                if target_role == Role.ADMIN:
                    profile.department = 'PWD Headquarters'
                    changed = True
                elif target_role == Role.FIELD_OFFICER:
                    profile.department = 'PWD Field Operations'
                    changed = True
                elif target_role == Role.NORMAL_USER:
                    profile.department = 'Logistics & Transport'
                    changed = True

            if changed:
                profile.save()
                updated_count += 1
                self.stdout.write(f"  Synced {user.username:<20} -> {target_role} (staff={user.is_staff})")

        self.stdout.write(self.style.SUCCESS(
            f"\nSync complete: {updated_count} user(s) updated, {created_profiles} profile(s) created."
        ))
