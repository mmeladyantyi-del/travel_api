"""Query filters for trip itineraries."""

import django_filters

from .models import Itinerary


class ItineraryFilter(django_filters.FilterSet):
    """Filter itineraries by status, destination, and date boundaries."""

    starts_after = django_filters.DateFilter(field_name='start_date', lookup_expr='gte')
    starts_before = django_filters.DateFilter(field_name='start_date', lookup_expr='lte')
    ends_after = django_filters.DateFilter(field_name='end_date', lookup_expr='gte')
    ends_before = django_filters.DateFilter(field_name='end_date', lookup_expr='lte')
    destination_id = django_filters.NumberFilter(field_name='destination_id')

    class Meta:
        model = Itinerary
        fields = ('status', 'owner')
