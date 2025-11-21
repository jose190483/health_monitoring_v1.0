from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings
from django.utils import timezone

BUSINESS_UNITS = [
    ('TPS', 'TPS'),
    ('OFS', 'OFS'),
    ('OFE', 'OFE'),
    ('Admin', 'Admin'),
]

class CustomUserManager(BaseUserManager):
    def create_user(self, email, phone_number, business_unit, password=None):
        if not email:
            raise ValueError('Users must have an email address')
        email = self.normalize_email(email)
        user = self.model(email=email, phone_number=phone_number, business_unit=business_unit)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, phone_number='0000000000', business_unit='Admin', password=None):
        user = self.create_user(email=email, phone_number=phone_number, business_unit=business_unit, password=password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15)
    business_unit = models.CharField(max_length=20, choices=BUSINESS_UNITS)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number', 'business_unit']

    def __str__(self):
        return f"{self.email} ({self.business_unit})"

# ---------- SERVER ----------
class ServerMetricsHistory(models.Model):
    file_name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255)
    data = models.JSONField()
    business_unit = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.hostname} ({self.business_unit}) @ {self.created_at:%Y-%m-%d %H:%M:%S}"

class ServerMetricsLive(models.Model):
    hostname = models.CharField(max_length=255, unique=True)
    business_unit = models.CharField(max_length=50)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.hostname} ({self.business_unit})"


class ServiceMetricsHistory(models.Model):
    file_name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255)
    data = models.JSONField()
    business_unit = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.hostname} ({self.business_unit}) @ {self.created_at:%Y-%m-%d %H:%M:%S}"

class ServiceMetricsLive(models.Model):
    hostname = models.CharField(max_length=255, unique=True)
    business_unit = models.CharField(max_length=50)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.hostname} ({self.business_unit})"


# ---------- SERVICE COMPONENT DETAILS----------
class ServiceComponentHistory(models.Model):
    file_name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255, blank=True, null=True)
    data = models.JSONField()
    business_unit = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.hostname or self.file_name} ({self.business_unit})"

class ServiceComponentLive(models.Model):
    hostname = models.CharField(max_length=255, unique=True)
    business_unit = models.CharField(max_length=50)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.hostname} ({self.business_unit})"


# ---------- APPLICATION METRICS ----------
class ApplicationDashboardHistory(models.Model):
    file_name = models.CharField(max_length=255)
    app_name = models.CharField(max_length=255)
    data = models.JSONField()
    business_unit = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.app_name} ({self.business_unit}) @ {self.created_at:%Y-%m-%d %H:%M:%S}"

class ApplicationDashboardLive(models.Model):
    app_name = models.CharField(max_length=255, unique=True)
    business_unit = models.CharField(max_length=50)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.app_name} ({self.business_unit})"

class ApplicationListHistory(models.Model):
    file_name = models.CharField(max_length=255)
    app_name = models.CharField(max_length=255)
    data = models.JSONField()
    business_unit = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.app_name} ({self.business_unit}) @ {self.created_at:%Y-%m-%d %H:%M:%S}"

class ApplicationListLive(models.Model):
    app_name = models.CharField(max_length=255, unique=True)
    business_unit = models.CharField(max_length=50)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.app_name} ({self.business_unit})"
