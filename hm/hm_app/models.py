from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings

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

# Create your models here.
class XMLData(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    business_unit = models.CharField(max_length=20, null=True, blank=True)
    file_name = models.CharField(max_length=255)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file_name


class ServiceComponentData(models.Model):
    file_name = models.CharField(max_length=255)
    data = models.JSONField()
    business_unit = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True, help_text="User who uploaded (if any)")

    def __str__(self):
        return f"{self.file_name} ({self.business_unit})"


class ApplicationData(models.Model):
    file_name = models.CharField(max_length=255)
    data = models.JSONField()
    business_unit = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file_name
