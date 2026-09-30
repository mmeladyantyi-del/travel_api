"""Trip search, itinerary CRUD, collaboration, and analytics endpoints."""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from budgets.models import Budget
from travel_api.pagination import StandardResultsSetPagination
from .filters import ItineraryFilter
from .models import ActivityLog, Collaboration, DailyPlan, Itinerary
from .permissions import CanEditItinerary, IsTripOwner, IsTripOwnerOrCollaborator
from .serializers import (
    CollaborationSerializer,
    CollaborationRoleUpdateSerializer,
    CollaborationRemovalSerializer,
    BookingBulkUpdateRequestSerializer,
    BookingBulkUpdateResponseSerializer,
    ItineraryDetailSerializer,
    ItineraryListSerializer,
    ItinerarySearchPageSerializer,
    ItinerarySearchParamsSerializer,
    ItineraryWriteSerializer,
    ItineraryPDFUploadSerializer,
    TripAnalyticsSummarySerializer,
    TripBudgetSummarySerializer,
    TripReportSerializer,
)

def _visible_itineraries(user):
    """Return trips owned by or shared with the given authenticated user."""
    return Itinerary.objects.filter(
        Q(owner=user) | Q(collaborations__user=user),
    ).distinct()


@extend_schema(
    methods=['GET'], parameters=[ItinerarySearchParamsSerializer],
    responses=ItinerarySearchPageSerializer,
)
@extend_schema(
    methods=['POST'], request=ItinerarySearchParamsSerializer,
    responses=ItinerarySearchPageSerializer,
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def trip_search(request):
    """Search accessible trips with GET filters or POSTed search criteria."""
    params = request.query_params if request.method == 'GET' else request.data
    if request.method == 'POST' and not isinstance(params, dict):
        raise ValidationError({'detail': 'Search body must be a JSON object.'})
    queryset = _visible_itineraries(request.user).select_related(
        'owner', 'destination',
    ).prefetch_related('daily_plans', 'collaborations').annotate(
        collaborator_count=Count('collaborations', distinct=True),
    ).order_by('-start_date', 'title')
    filterset = ItineraryFilter(data=params, queryset=queryset)
    if not filterset.is_valid():
        raise ValidationError(filterset.errors)
    queryset = filterset.qs
    term = params.get('search', '').strip()
    if term:
        queryset = queryset.filter(
            Q(title__icontains=term)
            | Q(description__icontains=term)
            | Q(destination__name__icontains=term)
        )
    ordering = params.get('ordering')
    if ordering in {'start_date', '-start_date', 'created_at', '-created_at', 'title', '-title'}:
        queryset = queryset.order_by(ordering)
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = ItineraryListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@extend_schema(responses=TripReportSerializer)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_trip_report(request, trip_id):
    """Combine itinerary, day-plan, booking, and budget totals into a report."""
    itinerary = get_object_or_404(
        _visible_itineraries(request.user).select_related('destination', 'owner').prefetch_related(
            'daily_plans__activities', 'collaborations__user',
            'bookings__accommodation', 'bookings__activity',
        ),
        pk=trip_id,
    )
    days = itinerary.daily_plans.annotate(activity_count=Count('activities')).values(
        'id', 'day_number', 'date', 'title', 'activity_count',
    )
    booking_totals = itinerary.bookings.aggregate(
        count=Count('id'),
        total=Sum('total_price'),
        pending=Count('id', filter=Q(status=Booking.Status.PENDING)),
    )
    budget = Budget.objects.filter(itinerary=itinerary).first()
    expense_total = budget.expenses.aggregate(total=Sum('amount'))['total'] if budget else None
    report = {
        'itinerary': ItineraryDetailSerializer(itinerary, context={'request': request}).data,
        'daily_plans': list(days),
        'bookings': {
            'count': booking_totals['count'],
            'total_price': booking_totals['total'] or 0,
            'pending_count': booking_totals['pending'],
        },
        'budget': {
            'planned': budget.total_amount if budget else itinerary.budget_amount,
            'currency': budget.currency if budget else itinerary.currency,
            'spent': expense_total or 0,
        },
    }
    return Response(report)


@extend_schema(
    request=BookingBulkUpdateRequestSerializer,
    responses=BookingBulkUpdateResponseSerializer,
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_update_bookings(request):
    """Update owned bookings atomically and report individual outcomes."""
    entries = request.data.get('bookings') if isinstance(request.data, dict) else request.data
    if not isinstance(entries, list) or not entries:
        raise ValidationError({'bookings': 'Provide a non-empty list of booking updates.'})
    if len(entries) > 100:
        raise ValidationError({'bookings': 'At most 100 bookings may be updated at once.'})

    results = []
    successes = failures = 0
    allowed_statuses = {choice for choice, _label in Booking.Status.choices}
    with transaction.atomic():
        for entry in entries:
            if not isinstance(entry, dict):
                failures += 1
                results.append({'id': None, 'success': False, 'error': 'Each entry must be an object.'})
                continue
            try:
                booking_id = int(entry.get('id'))
                new_status = entry.get('status')
                if new_status not in allowed_statuses:
                    raise ValueError('Invalid booking status.')
                with transaction.atomic():
                    booking = Booking.objects.select_for_update().get(
                        pk=booking_id, user=request.user,
                    )
                    booking.status = new_status
                    booking.full_clean()
                    booking.save(update_fields=['status', 'updated_at'])
                successes += 1
                results.append({'id': booking.pk, 'success': True, 'status': booking.status})
            except (Booking.DoesNotExist, DjangoValidationError, TypeError, ValueError) as exc:
                failures += 1
                results.append({'id': entry.get('id'), 'success': False, 'error': str(exc)})
    return Response(
        {'success_count': successes, 'failure_count': failures, 'results': results},
        status=status.HTTP_200_OK,
    )


class ItineraryListCreateView(generics.ListCreateAPIView):
    """List accessible itineraries or create one owned by the current user."""

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ItineraryFilter
    search_fields = ['title', 'description', 'destination__name']
    ordering_fields = ['created_at', 'start_date', 'end_date', 'title', 'budget_amount']
    ordering = ['-start_date']

    def get_queryset(self):
        """Scope trips to the user and optimize their list representation."""
        if getattr(self, 'swagger_fake_view', False):
            return Itinerary.objects.none()
        return _visible_itineraries(self.request.user).select_related(
            'owner', 'destination',
        ).prefetch_related(
            'daily_plans', 'collaborations', 'bookings',
        ).annotate(
            collaborator_count=Count('collaborations', distinct=True),
        ).defer('description')

    def get_serializer_class(self):
        """Use a compact card for list requests and a write serializer for creation."""
        return ItineraryListSerializer if self.request.method == 'GET' else ItineraryWriteSerializer

    def perform_create(self, serializer):
        """Assign ownership from the authenticated request, never request data."""
        serializer.save(owner=self.request.user)


class ItineraryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete an itinerary visible to the current user."""

    permission_classes = [IsAuthenticated, IsTripOwnerOrCollaborator, CanEditItinerary]

    def get_queryset(self):
        """Load trip relations needed for detail serialization and permissions."""
        if getattr(self, 'swagger_fake_view', False):
            return Itinerary.objects.none()
        return _visible_itineraries(self.request.user).select_related(
            'owner', 'destination',
        ).prefetch_related(
            'daily_plans__activities', 'collaborations__user',
            'bookings__accommodation', 'bookings__activity',
        ).annotate(collaborator_count=Count('collaborations', distinct=True))

    def get_serializer_class(self):
        """Return nested details on GET and validated fields on writes."""
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return ItineraryDetailSerializer
        return ItineraryWriteSerializer


class TripCollaborationView(APIView):
    """Let trip owners add, change, or remove collaborators."""

    permission_classes = [IsAuthenticated, IsTripOwner]

    def _get_owned_itinerary(self, request, trip_id):
        """Load a trip and explicitly run the owner object-permission check."""
        itinerary = get_object_or_404(Itinerary.objects.select_related('owner'), pk=trip_id)
        self.check_object_permissions(request, itinerary)
        return itinerary

    @extend_schema(request=CollaborationSerializer, responses={201: CollaborationSerializer})
    def post(self, request, trip_id):
        """Add a collaborator with an editor or viewer role."""
        itinerary = self._get_owned_itinerary(request, trip_id)
        serializer = CollaborationSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data['user'] == itinerary.owner:
            raise ValidationError({'user_id': 'The trip owner cannot be added as a collaborator.'})
        collaboration = serializer.save(itinerary=itinerary)
        ActivityLog.objects.create(
            itinerary=itinerary, actor=request.user, action=ActivityLog.Action.SHARED,
            details={'collaborator_id': collaboration.user_id, 'role': collaboration.role},
        )
        return Response(
            CollaborationSerializer(collaboration, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=CollaborationRoleUpdateSerializer, responses=CollaborationSerializer)
    def patch(self, request, trip_id):
        """Change the role of an existing collaborator."""
        itinerary = self._get_owned_itinerary(request, trip_id)
        serializer = CollaborationRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data['user_id'].pk
        collaboration = get_object_or_404(
            Collaboration.objects.select_related('user'), itinerary=itinerary, user_id=user_id,
        )
        collaboration.role = serializer.validated_data['role']
        collaboration.save(update_fields=['role'])
        return Response(CollaborationSerializer(collaboration).data)

    @extend_schema(request=CollaborationRemovalSerializer, responses={204: None})
    def delete(self, request, trip_id):
        """Remove a collaborator from the selected itinerary."""
        itinerary = self._get_owned_itinerary(request, trip_id)
        serializer = CollaborationRemovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data['user_id'].pk
        collaboration = get_object_or_404(
            Collaboration.objects.select_related('user'), itinerary=itinerary, user_id=user_id,
        )
        collaboration.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ItineraryPDFUploadView(APIView):
    """Upload a validated PDF for an itinerary the user can edit."""

    permission_classes = [IsAuthenticated, IsTripOwnerOrCollaborator, CanEditItinerary]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=ItineraryPDFUploadSerializer, responses=ItineraryPDFUploadSerializer)
    def post(self, request, trip_id):
        """Validate and save the itinerary PDF document."""
        itinerary = get_object_or_404(
            Itinerary.objects.select_related('owner'), pk=trip_id,
        )
        self.check_object_permissions(request, itinerary)
        serializer = ItineraryPDFUploadSerializer(
            itinerary, data=request.data, partial=True, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        itinerary = serializer.save()
        ActivityLog.objects.create(
            itinerary=itinerary, actor=request.user, action=ActivityLog.Action.UPDATED,
            details={'uploaded_file': 'itinerary_pdf'},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class ItineraryViewSet(viewsets.ModelViewSet):
    """Manage user trips with duplication, sharing, and upcoming-trip actions."""

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ItineraryFilter
    search_fields = ['title', 'description', 'destination__name']
    ordering_fields = ['created_at', 'start_date', 'end_date', 'title', 'budget_amount']
    ordering = ['-start_date']
    queryset = Itinerary.objects.none()

    def get_queryset(self):
        """Return only trips visible to the user with related data preloaded."""
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        queryset = _visible_itineraries(self.request.user).select_related(
            'owner', 'destination',
        ).prefetch_related(
            'daily_plans__activities', 'collaborations__user', 'bookings',
        ).annotate(collaborator_count=Count('collaborations', distinct=True))
        return queryset.defer('description') if self.action == 'list' else queryset

    def get_serializer_class(self):
        """Select compact, nested, or writable serializer by action."""
        if self.action in ('list', 'upcoming'):
            return ItineraryListSerializer
        if self.action == 'retrieve':
            return ItineraryDetailSerializer
        if self.action == 'share':
            return CollaborationSerializer
        return ItineraryWriteSerializer

    def get_permissions(self):
        """Require authentication and enforce collaborator roles on trip objects."""
        return [IsAuthenticated(), IsTripOwnerOrCollaborator(), CanEditItinerary()]

    def perform_create(self, serializer):
        """Assign the new trip to the authenticated owner."""
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Copy a trip and its day plans for the authenticated user."""
        original = self.get_object()
        with transaction.atomic():
            duplicate = Itinerary.objects.create(
                owner=request.user, destination=original.destination,
                title=f'{original.title} (copy)', description=original.description,
                start_date=original.start_date, end_date=original.end_date,
                budget_amount=original.budget_amount, currency=original.currency,
            )
            for day in original.daily_plans.prefetch_related('activities'):
                new_day = DailyPlan.objects.create(
                    itinerary=duplicate, day_number=day.day_number,
                    date=day.date, title=day.title, notes=day.notes,
                )
                new_day.activities.set(day.activities.all())
        return Response(
            ItineraryDetailSerializer(duplicate, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Share a trip with another user at the requested role."""
        itinerary = self.get_object()
        serializer = CollaborationSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data['user'] == itinerary.owner:
            raise ValidationError({'user_id': 'The trip owner cannot be added as a collaborator.'})
        collaboration = serializer.save(itinerary=itinerary)
        ActivityLog.objects.create(
            itinerary=itinerary, actor=request.user, action=ActivityLog.Action.SHARED,
            details={'collaborator_id': collaboration.user_id, 'role': collaboration.role},
        )
        return Response(
            CollaborationSerializer(collaboration, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """List accessible trips that have not started yet."""
        queryset = self.filter_queryset(self.get_queryset()).filter(
            Q(start_date__gte=timezone.localdate())
            & ~Q(status=Itinerary.Status.COMPLETED)
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class TripAnalyticsViewSet(viewsets.ViewSet):
    """Summarize the signed-in user's itinerary and budget activity."""

    permission_classes = [IsAuthenticated]
    serializer_class = TripAnalyticsSummarySerializer

    def get_queryset(self):
        """Return visible trips with a queryable planned budget value."""
        return _visible_itineraries(self.request.user).annotate(active_budget=F('budget_amount'))

    def list(self, request):
        """Return trip counts, status totals, and planned budget totals."""
        summary = self.get_queryset().aggregate(
            itinerary_count=Count('id', distinct=True),
            total_planned_budget=Sum(F('active_budget')),
            planning_count=Count('id', filter=Q(status=Itinerary.Status.PLANNING), distinct=True),
            booked_count=Count('id', filter=Q(status=Itinerary.Status.BOOKED), distinct=True),
        )
        summary['total_planned_budget'] = summary['total_planned_budget'] or 0
        return Response(summary)

    @action(detail=False, methods=['get'])
    @extend_schema(responses=TripBudgetSummarySerializer)
    def budget_summary(self, request):
        """Compare visible itinerary budgets with recorded expenses."""
        budgets = Budget.objects.filter(
            Q(itinerary__owner=request.user)
            | Q(itinerary__collaborations__user=request.user)
        ).annotate(
            spent=Coalesce(Sum('expenses__amount'), Decimal('0')),
        ).select_related('itinerary').distinct().values('total_amount', 'spent')
        summary = {
            'total_budget': Decimal('0'),
            'total_spent': Decimal('0'),
            'total_remaining': Decimal('0'),
        }
        for budget in budgets:
            summary['total_budget'] += budget['total_amount']
            summary['total_spent'] += budget['spent']
            summary['total_remaining'] += budget['total_amount'] - budget['spent']
        return Response(summary)
