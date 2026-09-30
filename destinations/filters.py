"""Query filters for browsing destination catalog entries."""

import django_filters

from .models import Destination


class DestinationFilter(django_filters.FilterSet):
    """Filter destinations by location, type, climate, and rating range."""

    name = django_filters.CharFilter(field_name='name', lookup_expr='icontains')
    country = django_filters.CharFilter(field_name='country', lookup_expr='icontains')
    min_rating = django_filters.NumberFilter(field_name='average_rating', lookup_expr='gte')
    max_rating = django_filters.NumberFilter(field_name='average_rating', lookup_expr='lte')

    class Meta:
        model = Destination
        fields = ('category', 'climate')
