"""Destination search and read-only catalog endpoints."""

from django.db.models import Avg, Count, Prefetch, Q
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from travel_api.pagination import StandardResultsSetPagination
from .filters import DestinationFilter
from .models import Accommodation, Activity, Destination
from .serializers import (
    ActivitySerializer,
    DestinationDetailSerializer,
    DestinationListSerializer,
    DestinationSearchPageSerializer,
    DestinationSearchParamsSerializer,
)


def _destination_search(queryset, params):
    """Apply shared text and structured filters to a destination queryset."""
    filterset = DestinationFilter(data=params, queryset=queryset)
    if not filterset.is_valid():
        raise ValidationError(filterset.errors)
    queryset = filterset.qs
    search_term = params.get('search', '').strip()
    if search_term:
        queryset = queryset.filter(
            Q(name__icontains=search_term)
            | Q(country__icontains=search_term)
            | Q(description__icontains=search_term)
        )
    return queryset


class DestinationSearchView(APIView):
    """Search destinations with GET query parameters or a POST search body."""

    permission_classes = [IsAuthenticatedOrReadOnly]

    def _search(self, request, params):
        """Filter and paginate destination cards for either supported method."""
        queryset = Destination.objects.annotate(
            active_activity_count=Count(
                'activities', filter=Q(activities__is_active=True), distinct=True,
            ),
            active_accommodation_count=Count(
                'accommodations', filter=Q(accommodations__is_active=True), distinct=True,
            ),
            review_count=Count('reviews', distinct=True),
            computed_rating=Avg('reviews__rating'),
        ).order_by('name')
        queryset = _destination_search(queryset, params)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = DestinationListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        parameters=[DestinationSearchParamsSerializer],
        responses=DestinationSearchPageSerializer,
    )
    def get(self, request):
        """Return matching destinations using URL query parameters."""
        return self._search(request, request.query_params)

    @extend_schema(
        request=DestinationSearchParamsSerializer,
        responses=DestinationSearchPageSerializer,
    )
    def post(self, request):
        """Return matching destinations using a JSON search body."""
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'Search body must be a JSON object.'})
        return self._search(request, request.data)


class DestinationViewSet(viewsets.ReadOnlyModelViewSet):
    """Browse destinations and their most popular activities."""

    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = DestinationFilter
    search_fields = ['name', 'description', 'country']
    ordering_fields = ['name', 'country', 'average_rating', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        """Prefetch destination resources and annotate counts used in responses."""
        activity_fields = (
            'id', 'destination_id', 'name', 'description', 'duration_minutes',
            'price', 'currency', 'is_active', 'created_at', 'updated_at',
        )
        accommodation_fields = (
            'id', 'destination_id', 'name', 'description', 'address',
            'nightly_rate', 'currency', 'photo', 'is_active', 'created_at',
            'updated_at',
        )
        return Destination.objects.annotate(
            active_activity_count=Count(
                'activities', filter=Q(activities__is_active=True), distinct=True,
            ),
            active_accommodation_count=Count(
                'accommodations', filter=Q(accommodations__is_active=True), distinct=True,
            ),
            review_count=Count('reviews', distinct=True),
            computed_rating=Avg('reviews__rating'),
        ).prefetch_related(
            Prefetch(
                'activities',
                queryset=Activity.objects.filter(is_active=True).only(*activity_fields),
            ),
            Prefetch(
                'accommodations',
                queryset=Accommodation.objects.filter(is_active=True).only(*accommodation_fields),
            ),
            'reviews',
        )

    def get_serializer_class(self):
        """Use nested resource details only for a single destination."""
        if self.action == 'retrieve':
            return DestinationDetailSerializer
        return DestinationListSerializer

    @action(detail=True, methods=['get'], url_path='popular-activities')
    def popular_activities(self, request, pk=None):
        """Return this destination's activities ranked by booking count."""
        activities = Activity.objects.filter(
            destination=self.get_object(), is_active=True,
        ).annotate(booking_count=Count('bookings')).order_by('-booking_count', 'name')
        page = self.paginate_queryset(activities)
        serializer = ActivitySerializer(page if page is not None else activities, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
