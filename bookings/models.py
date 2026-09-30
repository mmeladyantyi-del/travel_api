"""Booking records for itinerary accommodation and activities."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Booking(models.Model):
    """A user's reservation for one accommodation or activity."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    itinerary = models.ForeignKey(
        'itineraries.Itinerary', on_delete=models.SET_NULL,
        related_name='bookings', null=True, blank=True,
    )
    accommodation = models.ForeignKey(
        'destinations.Accommodation', on_delete=models.SET_NULL,
        related_name='bookings', null=True, blank=True,
    )
    activity = models.ForeignKey(
        'destinations.Activity', on_delete=models.SET_NULL,
        related_name='bookings', null=True, blank=True,
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    quantity = models.PositiveSmallIntegerField(default=1)
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default='ZAR')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    confirmation_code = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['itinerary', 'start_date']),
        ]

    def __str__(self):
        """Return a concise booking label."""
        return f'Booking {self.pk or "(unsaved)"} - {self.status}'

    def clean(self):
        """Require exactly one bookable item and a valid date range."""
        super().clean()
        # XOR rejects both missing targets and ambiguous bookings with two targets.
        if bool(self.accommodation_id) == bool(self.activity_id):
            raise ValidationError('Select exactly one accommodation or activity.')
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})

    def confirm(self):
        """Mark a pending booking as confirmed and persist the change."""
        self.status = self.Status.CONFIRMED
        self.save(update_fields=['status', 'updated_at'])
