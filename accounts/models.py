"""Account models for the travel planning API."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A travel API user with basic profile and audit fields."""

    email = models.EmailField(
        unique=True,
        help_text='A unique email address used for account communication.',
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        help_text='Optional phone number for travel-related contact.',
    )
    preferred_currency = models.CharField(
        max_length=3,
        default='ZAR',
        help_text='Three-letter currency code used for trip budgets.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['username']
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        """Return the user's display name, falling back to username."""
        return self.get_full_name() or self.username
