import random
import string
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, Role


class ProfileSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    approval_status_display = serializers.CharField(
        source='get_approval_status_display', read_only=True
    )

    class Meta:
        model = Profile
        fields = (
            'role', 'role_display',
            'approval_status', 'approval_status_display',
            'phone', 'department', 'created_at', 'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'profile')
        read_only_fields = ('id', 'is_superuser')


class UserRoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices, required=True)
    department = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    is_staff = serializers.BooleanField(required=False)


# Roles allowed for public self-registration (admin is excluded intentionally)
REGISTERABLE_ROLES = [
    (Role.NORMAL_USER, Role.NORMAL_USER.label),
    (Role.FIELD_OFFICER, Role.FIELD_OFFICER.label),
]


def _generate_username_suggestions(base: str, count: int = 3) -> list:
    """Generate unique username suggestions by appending random 2-char suffixes."""
    chars = string.digits + string.ascii_lowercase
    suggestions = []
    attempts = 0
    while len(suggestions) < count and attempts < 30:
        suffix = ''.join(random.choices(chars, k=2))
        candidate = f"{base}_{suffix}"
        if not User.objects.filter(username=candidate).exists():
            suggestions.append(candidate)
        attempts += 1
    return suggestions


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6, max_length=128)
    role = serializers.ChoiceField(choices=REGISTERABLE_ROLES, default=Role.NORMAL_USER)
    phone = serializers.CharField(required=False, default='', allow_blank=True)
    department = serializers.CharField(required=False, default='', allow_blank=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name', 'role', 'phone', 'department')
        extra_kwargs = {
            'username': {
                'validators': [],  # Custom validate_username handles uniqueness + suggestions
            }
        }

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            suggestions = _generate_username_suggestions(value)
            raise serializers.ValidationError({
                'message': f"Username '{value}' is already taken.",
                'suggestions': suggestions,
            })
        return value

    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError("Email address is required.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email address already exists. "
                "Please use a different email or log in."
            )
        return value.lower()

    def validate_phone(self, value):
        if value and Profile.objects.filter(phone=value).exists():
            raise serializers.ValidationError(
                "This phone number is already registered with another account."
            )
        return value

    def create(self, validated_data):
        from .models import ApprovalStatus
        role = validated_data.pop('role', Role.NORMAL_USER)
        phone = validated_data.pop('phone', '')
        department = validated_data.pop('department', '')

        user = User.objects.create_user(**validated_data)

        # Field Officers start as PENDING — admin must approve before they can log in
        if role == Role.FIELD_OFFICER:
            approval_status = ApprovalStatus.PENDING
        else:
            approval_status = ApprovalStatus.APPROVED

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = role
        profile.phone = phone
        profile.department = department
        profile.approval_status = approval_status
        profile.save()

        user.refresh_from_db()
        return user


