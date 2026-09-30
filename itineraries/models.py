"""Models for itineraries, collaboration, daily plans, and audit events."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Itinerary(models.Model):
    """A trip plan owned by a user and optionally shared with collaborators."""

    class Status(models.TextChoices):
        PLANNING = 'planning', 'Planning'
        BOOKED = 'booked', 'Booked'
        COMPLETED = 'completed', 'Completed'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='itineraries',
    )
    destination = models.ForeignKey(
        'destinations.Destination', on_delete=models.PROTECT,
        related_name='itineraries', null=True, blank=True,
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNING)
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='ZAR')
    collaborators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='Collaboration',
        related_name='collaborative_itineraries', blank=True,
    )
    itinerary_pdf = models.FileField(upload_to='itineraries/pdfs/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', 'title']
        indexes = [
            models.Index(fields=['owner', 'start_date']),
            models.Index(fields=['status', 'start_date']),
        ]

    def __str__(self):
        """Return the itinerary title and travel date range."""
        return f'{self.title} ({self.start_date} to {self.end_date})'

    def clean(self):
        """Ensure the trip's date range is valid."""
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})

    @property
    def duration_days(self):
        """Return the inclusive number of trip days."""
        if not self.start_date or not self.end_date:
            return 0
        return (self.end_date - self.start_date).days + 1


class Collaboration(models.Model):
    """A user's role on an itinerary, used as the M2M through model."""

    class Role(models.TextChoices):
        EDITOR = 'editor', 'Editor'
        VIEWER = 'viewer', 'Viewer'

    itinerary = models.ForeignKey(
        Itinerary, on_delete=models.CASCADE, related_name='collaborations',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='trip_collaborations',
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VIEWER)
    invited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['invited_at']
        constraints = [
            models.UniqueConstraint(fields=['itinerary', 'user'], name='unique_itinerary_collaborator'),
        ]

    def __str__(self):
        """Return the collaborator, role, and itinerary."""
        return f'{self.user} - {self.role} on {self.itinerary.title}'


class DailyPlan(models.Model):
    """A day within an itinerary, optionally containing planned activities."""

    itinerary = models.ForeignKey(
        Itinerary, on_delete=models.CASCADE, related_name='daily_plans',
    )
    day_number = models.PositiveSmallIntegerField()
    date = models.DateField()
    title = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    activities = models.ManyToManyField(
        'destinations.Activity', related_name='daily_plans', blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['itinerary', 'day_number']
        constraints = [
            models.UniqueConstraint(fields=['itinerary', 'day_number'], name='unique_itinerary_day_number'),
            models.UniqueConstraint(fields=['itinerary', 'date'], name='unique_itinerary_day_date'),
        ]
        indexes = [models.Index(fields=['itinerary', 'date'])]

    def __str__(self):
        """Return the day index and itinerary title."""
        return f'Day {self.day_number} - {self.itinerary.title}'

    def clean(self):
        """Ensure the planned date falls within the itinerary date range."""
        super().clean()
        if self.itinerary_id and self.date:
            if not self.itinerary.start_date <= self.date <= self.itinerary.end_date:
                raise ValidationError({'date': 'Plan date must fall within the itinerary dates.'})


class ActivityLog(models.Model):
    """An audit event describing a change made to an itinerary."""

    class Action(models.TextChoices):
        CREATED = 'created', 'Created'
        UPDATED = 'updated', 'Updated'
        SHARED = 'shared', 'Shared'
        BOOKED = 'booked', 'Booked'
        DELETED = 'deleted', 'Deleted'

    itinerary = models.ForeignKey(
        Itinerary, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activity_logs',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activity_logs',
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        """Return the action and itinerary identifier for audit lists."""
        return f'{self.action} itinerary {self.itinerary_id or "(removed)"}'
