"""Serializers for creating and reviewing travel bookings."""

from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from destinations.serializers import AccommodationSerializer, ActivitySerializer
from .models import Booking


class BookingListSerializer(serializers.ModelSerializer):
    """Compact booking representation for account booking lists."""

    user = UserSummarySerializer(read_only=True)
    item_name = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            'id', 'user', 'itinerary', 'item_name', 'start_date', 'end_date',
            'quantity', 'total_price', 'currency', 'status', 'created_at',
        )
        read_only_fields = fields
        extra_kwargs = {
            'total_price': {'help_text': 'Total amount for the booking.'},
            'start_date': {'help_text': 'Date the booked service begins.'},
        }

    def get_item_name(self, obj) -> str | None:
        """Return the selected accommodation or activity name."""
        item = obj.accommodation or obj.activity
        return item.name if item else None


class BookingDetailSerializer(BookingListSerializer):
    """Booking response with nested service details."""

    accommodation_detail = AccommodationSerializer(source='accommodation', read_only=True)
    activity_detail = ActivitySerializer(source='activity', read_only=True)

    class Meta(BookingListSerializer.Meta):
        fields = BookingListSerializer.Meta.fields + (
            'accommodation_detail', 'activity_detail', 'confirmation_code',
            'notes', 'updated_at',
        )
        read_only_fields = fields

    def to_representation(self, instance):
        """Serialize the selected service along with its booking details."""
        return super().to_representation(instance)


class BookingWriteSerializer(serializers.ModelSerializer):
    """Create or update a booking while assigning its owner in the view."""

    class Meta:
        model = Booking
        fields = (
            'id', 'itinerary', 'accommodation', 'activity', 'start_date',
            'end_date', 'quantity', 'total_price', 'currency', 'status', 'notes',
        )
        read_only_fields = ('id', 'status')
        extra_kwargs = {
            'itinerary': {'help_text': 'Optional trip associated with this booking.'},
            'accommodation': {'help_text': 'Choose this for a lodging reservation.'},
            'activity': {'help_text': 'Choose this for an activity reservation.'},
            'quantity': {'help_text': 'Number of rooms or participants reserved.'},
        }

    def validate_quantity(self, value):
        """Require a positive booking quantity."""
        if value < 1:
            raise serializers.ValidationError('Quantity must be at least one.')
        return value

    def validate_total_price(self, value):
        """Reject negative booking totals."""
        if value < 0:
            raise serializers.ValidationError('Total price cannot be negative.')
        return value

    def validate(self, attrs):
        """Require one bookable item and a valid date range."""
        accommodation = attrs.get('accommodation', getattr(self.instance, 'accommodation', None))
        activity = attrs.get('activity', getattr(self.instance, 'activity', None))
        if bool(accommodation) == bool(activity):
            raise serializers.ValidationError('Select exactly one accommodation or activity.')
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if end and start and end < start:
            raise serializers.ValidationError({'end_date': 'End date cannot be before start date.'})
        return attrs

    def create(self, validated_data):
        """Create a booking for the authenticated request user."""
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            raise serializers.ValidationError('An authenticated booking owner is required.')
        user = validated_data.pop('user', request.user)
        return Booking.objects.create(user=user, **validated_data)
