"""Query filters for user bookings."""

import django_filters

from .models import Booking


class BookingFilter(django_filters.FilterSet):
    """Filter bookings by status, itinerary, date, and amount."""

    itinerary_id = django_filters.NumberFilter(field_name='itinerary_id')
    starts_after = django_filters.DateFilter(field_name='start_date', lookup_expr='gte')
    starts_before = django_filters.DateFilter(field_name='start_date', lookup_expr='lte')
    min_total = django_filters.NumberFilter(field_name='total_price', lookup_expr='gte')
    max_total = django_filters.NumberFilter(field_name='total_price', lookup_expr='lte')
    service_type = django_filters.ChoiceFilter(
        choices=(('accommodation', 'Accommodation'), ('activity', 'Activity')),
        method='filter_service_type',
    )

    class Meta:
        model = Booking
        fields = ('status', 'user')

    def filter_service_type(self, queryset, name, value):
        """Return bookings matching the selected accommodation or activity type."""
        field_name = 'accommodation__isnull' if value == 'accommodation' else 'activity__isnull'
        return queryset.filter(**{field_name: False})
