"""Query filters for categorized trip expenses."""

import django_filters

from .models import Expense


class ExpenseFilter(django_filters.FilterSet):
    """Filter expenses by budget, category, date, and amount range."""

    spent_after = django_filters.DateFilter(field_name='spent_on', lookup_expr='gte')
    spent_before = django_filters.DateFilter(field_name='spent_on', lookup_expr='lte')
    min_amount = django_filters.NumberFilter(field_name='amount', lookup_expr='gte')
    max_amount = django_filters.NumberFilter(field_name='amount', lookup_expr='lte')

    class Meta:
        model = Expense
        fields = ('budget', 'category')
