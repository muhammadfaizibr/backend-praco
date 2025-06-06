from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser

class UserManager(BaseUserManager):
    def create_user(self, email, first_name, last_name, company_name=None, receive_marketing=False, password=None):
        """
        Creates and saves a User with the given email, first name, last name, company name, marketing preference, and password.
        """
        if not email:
            raise ValueError('Users must have an email address')
        if not first_name or not last_name:
            raise ValueError('First name and last name are required')

        user = self.model(
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            receive_marketing=receive_marketing
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name, last_name, password=None, company_name=None, receive_marketing=False):
        """
        Creates and saves a superuser with the given email, first name, last name, company name, marketing preference, and password.
        """
        user = self.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            receive_marketing=receive_marketing,
            password=password
        )
        user.is_admin = True
        user.is_active = True
        user.save(using=self._db)
        return user

class User(AbstractBaseUser):
    email = models.EmailField(
        verbose_name='Email',
        max_length=255,
        unique=True
    )
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    receive_marketing = models.BooleanField(default=False, verbose_name='Receive Marketing Communications')
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        """Does the user have a specific permission?"""
        return self.is_admin

    def has_module_perms(self, app_label):
        """Does the user have permissions to view the app `app_label`?"""
        return self.is_admin
    
    def get_full_name(self):
        """Return the user's full name by concatenating first_name and last_name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_staff(self):
        """Is the user a member of staff?"""
        return self.is_admin