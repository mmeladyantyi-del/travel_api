"""Reviews for destinations and activities."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """A user's rating and written feedback for one travel resource."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    destination = models.ForeignKey(
        'destinations.Destination', on_delete=models.SET_NULL,
        related_name='reviews', null=True, blank=True,
    )
    activity = models.ForeignKey(
        'destinations.Activity', on_delete=models.SET_NULL,
        related_name='reviews', null=True, blank=True,
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['destination', '-created_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'destination'], condition=models.Q(destination__isnull=False),
                name='unique_user_destination_review',
            ),
            models.UniqueConstraint(
                fields=['user', 'activity'], condition=models.Q(activity__isnull=False),
                name='unique_user_activity_review',
            ),
        ]

    def __str__(self):
        """Return the rating and reviewer username."""
        return f'{self.rating}/5 by {self.user}'

    def clean(self):
        """Require one existing review target; SET_NULL may clear a deleted target."""
        super().clean()
        if bool(self.destination_id) == bool(self.activity_id):
            raise ValidationError('A review must target exactly one destination or activity.')
