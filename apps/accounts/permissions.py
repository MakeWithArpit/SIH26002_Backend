from rest_framework.permissions import BasePermission
from .models import Role

class IsAdminRole(BasePermission):
    """Allows access only to users with the Admin role."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == Role.ADMIN))
        )

class IsFieldOfficer(BasePermission):
    """Allows access to users with Field Officer (or Admin) role."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (
                request.user.is_superuser or
                (hasattr(request.user, 'profile') and request.user.profile.role in (Role.FIELD_OFFICER, Role.ADMIN))
            )
        )

class IsNormalUser(BasePermission):
    """Allows access to any authenticated user."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
