"""Destination search and read-only catalog endpoints."""

from django.db.models import Avg, Case, Count, IntegerField, Prefetch, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.parsers import FormParser, MultiPartParser
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
    DestinationPhotoUploadSerializer,
    DestinationRecommendationPageSerializer,
    DestinationRecommendationQuerySerializer,
    DestinationRecommendationSerializer,
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
        """Return matching destinations using URL query parameters.

        Example: GET /api/v1/destinations/search/?country=South%20Africa
        """
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


class DestinationRecommendationView(APIView):
    """Rank destinations using the authenticated user's travel signals."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[DestinationRecommendationQuerySerializer],
        responses=DestinationRecommendationPageSerializer,
    )
    def get(self, request):
        """Recommend unvisited destinations matching trip and review history.

        Example: GET /api/v1/destinations/recommendations/?limit=5
        """
        params = DestinationRecommendationQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        options = params.validated_data
        user = request.user

        # Treat trips and strong reviews as positive preference signals.
        positive_destinations = Destination.objects.filter(
            Q(itineraries__owner=user)
            | Q(itineraries__collaborations__user=user)
            | Q(reviews__user=user, reviews__rating__gte=4)
            | Q(activities__reviews__user=user, activities__reviews__rating__gte=4)
        ).distinct()
        preferences = list(positive_destinations.values_list('category', 'country', 'climate'))
        preferred_categories = {category for category, _, _ in preferences if category}
        preferred_countries = {country for _, country, _ in preferences if country}
        preferred_climates = {climate for _, _, climate in preferences if climate}

        # Omit places the user has already planned or reviewed, while retaining them as preference evidence.
        visited_ids = set(
            user.itineraries.exclude(destination__isnull=True).values_list('destination_id', flat=True)
        )
        visited_ids.update(
            user.collaborative_itineraries.exclude(destination__isnull=True).values_list('destination_id', flat=True)
        )
        visited_ids.update(user.reviews.exclude(destination__isnull=True).values_list('destination_id', flat=True))
        visited_ids.update(
            user.reviews.exclude(activity__isnull=True).values_list('activity__destination_id', flat=True)
        )

        # Explicit filters act as additional positive signals and narrow the candidate pool.
        for field, preference_set in (
            ('country', preferred_countries),
            ('category', preferred_categories),
            ('climate', preferred_climates),
        ):
            selected = options.get(field)
            if selected:
                preference_set.add(selected)

        score = Value(0, output_field=IntegerField())
        for field, values, weight in (
            ('category', preferred_categories, 3),
            ('country', preferred_countries, 2),
            ('climate', preferred_climates, 1),
        ):
            if values:
                score += Case(
                    When(**{f'{field}__in': values}, then=Value(weight)),
                    default=Value(0), output_field=IntegerField(),
                )

        queryset = Destination.objects.annotate(
            active_activity_count=Count(
                'activities', filter=Q(activities__is_active=True), distinct=True,
            ),
            active_accommodation_count=Count(
                'accommodations', filter=Q(accommodations__is_active=True), distinct=True,
            ),
            review_count=Count('reviews', distinct=True),
            computed_rating=Avg('reviews__rating', distinct=True),
            recommendation_score=score,
        ).exclude(pk__in=visited_ids)
        for field in ('country', 'category', 'climate'):
            if options.get(field):
                queryset = queryset.filter(**{f'{field}__iexact': options[field]})

        # Rank and paginate in SQL so a large destination catalog stays bounded.
        paginator = StandardResultsSetPagination()
        paginator.page_size = options['limit']
        page = paginator.paginate_queryset(
            queryset.order_by('-recommendation_score', '-computed_rating', 'name'),
            request,
            view=self,
        )
        for destination in page:
            matched = []
            if destination.category in preferred_categories:
                matched.append(f"{destination.category} interests")
            if destination.country in preferred_countries:
                matched.append(f"{destination.country} trips")
            if destination.climate in preferred_climates:
                matched.append(f"{destination.climate} climate")
            destination.recommendation_reason = ', '.join(matched) or (
                'Highly rated by travelers' if destination.computed_rating and destination.computed_rating >= 4
                else 'Popular destination'
            )

        serializer = DestinationRecommendationSerializer(
            page, many=True, context={'request': request},
        )
        return paginator.get_paginated_response(serializer.data)


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
        # Counts are annotated once, while only the nested active records are prefetched.
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


class DestinationPhotoUploadView(APIView):
    """Upload a validated catalog photo for a destination."""

    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=DestinationPhotoUploadSerializer, responses=DestinationPhotoUploadSerializer)
    def post(self, request, pk):
        """Validate and save a primary destination image."""
        destination = get_object_or_404(Destination, pk=pk)
        serializer = DestinationPhotoUploadSerializer(
            destination, data=request.data, partial=True, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
