"""Trip budgets and individual travel expenses."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Budget(models.Model):
    """A one-to-one spending plan for an itinerary."""

    itinerary = models.OneToOneField(
        'itineraries.Itinerary', on_delete=models.CASCADE, related_name='budget',
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default='ZAR')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['itinerary']
        verbose_name_plural = 'budgets'

    def __str__(self):
        """Return the budget amount and associated trip title."""
        return f'{self.currency} {self.total_amount} for {self.itinerary.title}'

    def clean(self):
        """Ensure the total budget is non-negative."""
        super().clean()
        if self.total_amount is not None and self.total_amount < Decimal('0'):
            raise ValidationError({'total_amount': 'Budget cannot be negative.'})

    @property
    def spent_amount(self):
        """Sum recorded expenses without loading every expense object."""
        return self.expenses.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def remaining_amount(self):
        """Return the amount left after recorded expenses."""
        return self.total_amount - self.spent_amount


class Expense(models.Model):
    """A dated expense assigned to a trip budget."""

    class Category(models.TextChoices):
        ACCOMMODATION = 'accommodation', 'Accommodation'
        TRANSPORT = 'transport', 'Transport'
        FOOD = 'food', 'Food'
        ACTIVITY = 'activity', 'Activity'
        OTHER = 'other', 'Other'

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=180)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))],
    )
    spent_on = models.DateField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-spent_on', '-created_at']
        indexes = [models.Index(fields=['budget', 'category', 'spent_on'])]

    def __str__(self):
        """Return the expense description and amount."""
        return f'{self.description}: {self.amount} {self.budget.currency}'
