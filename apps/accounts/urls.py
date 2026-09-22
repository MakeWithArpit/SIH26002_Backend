from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView,
    UserProfileView,
    UserListView,
    UserRoleUpdateView,
    SyncRolesBulkView,
)

urlpatterns = [
    # Auth
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserProfileView.as_view(), name='user-profile'),

    # Role Management (Admin only)
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:user_id>/role/', UserRoleUpdateView.as_view(), name='user-role-update'),
    path('sync-roles/', SyncRolesBulkView.as_view(), name='user-sync-roles'),
]
