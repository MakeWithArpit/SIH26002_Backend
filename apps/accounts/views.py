from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.common.responses import standard_response
from .models import Profile, Role
from .permissions import IsAdminRole
from .serializers import RegisterSerializer, UserSerializer, UserRoleUpdateSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return standard_response(
            data=UserSerializer(user).data,
            message="User registered successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return standard_response(data=UserSerializer(request.user).data)


class UserListView(APIView):
    """
    List all users with their assigned roles and profiles.
    Restricted to Admin users.
    Supports filtering by ?role=admin|field_officer|normal_user and ?search=
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        queryset = User.objects.all().select_related('profile').order_by('id')

        role_filter = request.query_params.get('role')
        if role_filter:
            queryset = queryset.filter(profile__role=role_filter)

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(username__icontains=search) | queryset.filter(email__icontains=search)

        serializer = UserSerializer(queryset, many=True)
        return standard_response(
            data=serializer.data,
            message=f"Retrieved {queryset.count()} users.",
        )


class UserRoleUpdateView(APIView):
    """
    Update a user's role, department, phone, and staff status.
    Restricted to Admin users.
    """
    permission_classes = [IsAdminRole]

    def patch(self, request, user_id):
        target_user = get_object_or_404(User, id=user_id)
        serializer = UserRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        role = data['role']
        profile, _ = Profile.objects.get_or_create(user=target_user)
        profile.role = role

        if 'department' in data:
            profile.department = data['department']
        if 'phone' in data:
            profile.phone = data['phone']
        profile.save()

        # Handle staff status if specified, or auto-grant staff for admin role
        if 'is_staff' in data:
            target_user.is_staff = data['is_staff']
            target_user.save(update_fields=['is_staff'])
        elif role == Role.ADMIN and not target_user.is_staff:
            target_user.is_staff = True
            target_user.save(update_fields=['is_staff'])

        target_user.refresh_from_db()
        return standard_response(
            data=UserSerializer(target_user).data,
            message=f"Role for '{target_user.username}' updated to '{role}'.",
        )


class SyncRolesBulkView(APIView):
    """
    Bulk auto-synchronize roles for all existing users based on username conventions.
    admin_* -> admin (is_staff=True)
    fo_*    -> field_officer
    driver_* -> normal_user
    Restricted to Admin users.
    """
    permission_classes = [IsAdminRole]

    def post(self, request):
        updated_count = 0
        created_profiles = 0

        for user in User.objects.all():
            profile, created = Profile.objects.get_or_create(user=user)
            if created:
                created_profiles += 1

            uname = user.username.lower()
            changed = False

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
                target_role = profile.role or Role.NORMAL_USER

            if profile.role != target_role:
                profile.role = target_role
                changed = True

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

        return standard_response(
            data={
                'updated_users_count': updated_count,
                'created_profiles_count': created_profiles,
                'total_users': User.objects.count(),
            },
            message=f"Synchronized roles: {updated_count} users updated, {created_profiles} profiles created.",
        )
