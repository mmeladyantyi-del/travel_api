"""Serializers for trip budgets and categorized expenses."""

from rest_framework import serializers

from .models import Budget, Expense


class ExpenseSerializer(serializers.ModelSerializer):
    """Represent an expense with its budget reference."""

    class Meta:
        model = Expense
        fields = (
            'id', 'budget', 'category', 'description', 'amount', 'spent_on',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {
            'category': {'help_text': 'Expense category used in budget summaries.'},
            'amount': {'help_text': 'Expense amount in the budget currency.'},
            'spent_on': {'help_text': 'Date the expense was incurred.'},
        }

    def validate_amount(self, value):
        """Reject zero or negative expense amounts."""
        if value <= 0:
            raise serializers.ValidationError('Expense amount must be greater than zero.')
        return value


class BudgetSerializer(serializers.ModelSerializer):
    """Represent a trip budget with its expenses and computed totals."""

    itinerary_title = serializers.CharField(source='itinerary.title', read_only=True)
    expenses = ExpenseSerializer(many=True, read_only=True)
    spent_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = (
            'id', 'itinerary', 'itinerary_title', 'total_amount', 'currency',
            'notes', 'spent_amount', 'remaining_amount', 'expenses',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'itinerary_title', 'spent_amount', 'remaining_amount',
            'expenses', 'created_at', 'updated_at',
        )
        extra_kwargs = {
            'itinerary': {'help_text': 'Trip this budget tracks; each trip has one budget.'},
            'total_amount': {'help_text': 'Maximum planned trip spend.'},
            'currency': {'help_text': 'Three-letter currency code for all amounts.'},
        }

    def get_spent_amount(self, obj):
        """Return the total of all recorded expenses."""
        return obj.spent_amount

    def get_remaining_amount(self, obj):
        """Return the budget left after expenses."""
        return obj.remaining_amount

    def validate_total_amount(self, value):
        """Ensure the planned budget is not negative."""
        if value < 0:
            raise serializers.ValidationError('Budget cannot be negative.')
        return value
