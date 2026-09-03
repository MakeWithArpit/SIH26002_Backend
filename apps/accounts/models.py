from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Role(models.TextChoices):
    ADMIN = 'admin', 'Admin'
    FIELD_OFFICER = 'field_officer', 'Field Officer'
    NORMAL_USER = 'normal_user', 'Normal User'

class Profile(models.Model):
    """
    Profile extension for the Django User model as specified in the PRD.
    Stores role, phone, and metadata.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.NORMAL_USER,
        db_index=True
    )
    phone = models.CharField(max_length=20, blank=True, default='')
    department = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN

    @property
    def is_field_officer(self):
        return self.role == Role.FIELD_OFFICER

    @property
    def is_normal_user(self):
        return self.role == Role.NORMAL_USER


@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
