from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, Role

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ('role', 'phone', 'department', 'created_at', 'updated_at')
        read_only_fields = ('created_at', 'updated_at')

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'profile')
        read_only_fields = ('id',)

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(choices=Role.choices, default=Role.NORMAL_USER)
    phone = serializers.CharField(required=False, default='')
    department = serializers.CharField(required=False, default='')

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name', 'role', 'phone', 'department')

    def create(self, validated_data):
        role = validated_data.pop('role', Role.NORMAL_USER)
        phone = validated_data.pop('phone', '')
        department = validated_data.pop('department', '')
        
        user = User.objects.create_user(**validated_data)
        
        # Profile is created via signal, update role & details
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = role
        profile.phone = phone
        profile.department = department
        profile.save()
        
        user.refresh_from_db()
        return user
