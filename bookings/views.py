"""Booking detail and viewset endpoints."""

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsBookingOwner
from itineraries.models import ActivityLog
from .filters import BookingFilter
from .models import Booking
from .serializers import BookingDetailSerializer, BookingListSerializer, BookingWriteSerializer


class BookingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a booking owned by the current user."""

    permission_classes = [IsAuthenticated, IsBookingOwner]

    def get_queryset(self):
        """Limit bookings to their owner and preload related trip resources."""
        if getattr(self, 'swagger_fake_view', False):
            return Booking.objects.none()
        return Booking.objects.filter(user=self.request.user).select_related(
            'user', 'itinerary__destination', 'accommodation', 'activity__destination',
        ).prefetch_related('itinerary__daily_plans')

    def get_serializer_class(self):
        """Use a nested serializer for retrieval and a writable one for edits."""
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return BookingDetailSerializer
        return BookingWriteSerializer


class BookingViewSet(viewsets.ModelViewSet):
    """Manage personal bookings and confirm or cancel reservations."""

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = BookingFilter
    search_fields = ['confirmation_code', 'notes', 'accommodation__name', 'activity__name']
    ordering_fields = ['created_at', 'start_date', 'total_price', 'status']
    ordering = ['-created_at']
    queryset = Booking.objects.none()

    def get_queryset(self):
        """Scope results to the user and optimize list/detail related data."""
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        queryset = Booking.objects.filter(user=self.request.user).select_related(
            'user', 'itinerary', 'accommodation', 'activity',
        )
        if self.action == 'list':
            return queryset.only(
                'id', 'user_id', 'itinerary_id', 'accommodation_id', 'activity_id',
                'start_date', 'end_date', 'quantity', 'total_price', 'currency',
                'status', 'created_at', 'user__username', 'user__first_name',
                'user__last_name',
            )
        return queryset.select_related('itinerary__destination', 'activity__destination')

    def get_serializer_class(self):
        """Choose list, detail, or write representations by action."""
        if self.action == 'list':
            return BookingListSerializer
        if self.action == 'retrieve':
            return BookingDetailSerializer
        return BookingWriteSerializer

    def get_permissions(self):
        """Require authentication and explicit ownership checks for mutations."""
        permissions = [IsAuthenticated()]
        if self.action in {
            'retrieve', 'update', 'partial_update', 'destroy', 'confirm', 'cancel',
        }:
            permissions.append(IsBookingOwner())
        return permissions

    def perform_create(self, serializer):
        """Create the booking under the authenticated request user."""
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a pending booking and record the itinerary audit event."""
        booking = self.get_object()
        if booking.status != Booking.Status.PENDING:
            raise ValidationError({'status': 'Only pending bookings can be confirmed.'})
        with transaction.atomic():
            booking.confirm()
            if booking.itinerary_id:
                ActivityLog.objects.create(
                    itinerary=booking.itinerary, actor=request.user,
                    action=ActivityLog.Action.BOOKED,
                    details={'booking_id': booking.pk, 'status': booking.status},
                )
        return Response(BookingDetailSerializer(booking, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending or confirmed booking."""
        booking = self.get_object()
        if booking.status not in {Booking.Status.PENDING, Booking.Status.CONFIRMED}:
            raise ValidationError({'status': 'Only pending or confirmed bookings can be cancelled.'})
        # Persist the state change and audit record together to avoid partial cancellation.
        with transaction.atomic():
            booking.status = Booking.Status.CANCELLED
            booking.save(update_fields=['status', 'updated_at'])
            if booking.itinerary_id:
                ActivityLog.objects.create(
                    itinerary=booking.itinerary, actor=request.user,
                    action=ActivityLog.Action.UPDATED,
                    details={'booking_id': booking.pk, 'status': booking.status},
                )
        return Response(BookingDetailSerializer(booking, context=self.get_serializer_context()).data)
