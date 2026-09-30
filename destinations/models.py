"""Destination, accommodation, and activity catalog models."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Destination(models.Model):
    """A place users can visit and add to an itinerary."""

    name = models.CharField(max_length=120, unique=True, help_text='Display name of the destination.')
    slug = models.SlugField(max_length=140, unique=True)
    country = models.CharField(max_length=100, db_index=True)
    category = models.CharField(max_length=60, blank=True)
    climate = models.CharField(max_length=60, blank=True)
    description = models.TextField(blank=True)
    primary_photo = models.ImageField(upload_to='destinations/', blank=True, null=True)
    average_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['country', 'category'])]

    def __str__(self):
        """Return the destination and country for admin displays."""
        return f'{self.name}, {self.country}'


class Accommodation(models.Model):
    """A lodging option associated with a destination."""

    name = models.CharField(max_length=160)
    destination = models.ForeignKey(
        Destination, on_delete=models.CASCADE, related_name='accommodations',
    )
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    nightly_rate = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='ZAR')
    photo = models.ImageField(upload_to='accommodations/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['destination', 'is_active'])]

    def __str__(self):
        """Return the accommodation name and destination."""
        return f'{self.name} in {self.destination.name}'


class Activity(models.Model):
    """An attraction or activity available at a destination."""

    name = models.CharField(max_length=160)
    destination = models.ForeignKey(
        Destination, on_delete=models.CASCADE, related_name='activities',
    )
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='ZAR')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['destination', 'is_active'])]
        constraints = [
            models.UniqueConstraint(fields=['destination', 'name'], name='unique_activity_per_destination'),
        ]

    def __str__(self):
        """Return the activity name and destination."""
        return f'{self.name} in {self.destination.name}'
