"""Serializers for trip plans, collaboration, and scheduled days."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from bookings.models import Booking
from destinations.models import Activity
from destinations.serializers import ActivitySerializer
from travel_api.upload_validators import validate_pdf_upload
from .models import ActivityLog, Collaboration, DailyPlan, Itinerary

User = get_user_model()


class CollaborationSerializer(serializers.ModelSerializer):
    """Represent a collaborator and their itinerary role."""

    user = UserSummarySerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source='user', queryset=User.objects.all(),
        write_only=True, help_text='Account to add as an itinerary collaborator.',
    )

    class Meta:
        model = Collaboration
        fields = ('id', 'user', 'user_id', 'role', 'invited_at')
        read_only_fields = ('id', 'invited_at')


class CollaborationRoleUpdateSerializer(serializers.Serializer):
    """Validate collaborator identifiers and role changes."""

    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    role = serializers.ChoiceField(choices=Collaboration.Role.choices)


class CollaborationRemovalSerializer(serializers.Serializer):
    """Validate the collaborator identifier used for removal."""

    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())


class DailyPlanSerializer(serializers.ModelSerializer):
    """Serialize a planned day with nested activities and writable IDs."""

    activities = ActivitySerializer(many=True, read_only=True)
    activity_ids = serializers.PrimaryKeyRelatedField(
        queryset=Activity.objects.all(), many=True, required=False, write_only=True,
        help_text='Activity IDs to include in this day.',
    )

    class Meta:
        model = DailyPlan
        fields = (
            'id', 'itinerary', 'day_number', 'date', 'title', 'notes',
            'activities', 'activity_ids', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {
            'day_number': {'help_text': 'One-based day number within the itinerary.'},
            'date': {'help_text': 'Calendar date for this plan.'},
        }

    def validate(self, attrs):
        """Ensure the date belongs to the associated itinerary."""
        itinerary = attrs.get('itinerary', getattr(self.instance, 'itinerary', None))
        plan_date = attrs.get('date', getattr(self.instance, 'date', None))
        if itinerary and plan_date and not itinerary.start_date <= plan_date <= itinerary.end_date:
            raise serializers.ValidationError({'date': 'Date must fall within itinerary dates.'})
        return attrs

    def create(self, validated_data):
        """Create a daily plan and attach any submitted activities."""
        activities = validated_data.pop('activity_ids', [])
        plan = DailyPlan.objects.create(**validated_data)
        if activities:
            plan.activities.set(activities)
        return plan

    def update(self, instance, validated_data):
        """Update day fields and replace activities only when IDs are supplied."""
        activities = validated_data.pop('activity_ids', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if activities is not None:
            instance.activities.set(activities)
        return instance


class ItineraryListSerializer(serializers.ModelSerializer):
    """Compact itinerary card with owner and destination display values."""

    owner = UserSummarySerializer(read_only=True)
    destination_name = serializers.SerializerMethodField()
    duration_days = serializers.SerializerMethodField()
    collaborator_count = serializers.SerializerMethodField()

    class Meta:
        model = Itinerary
        fields = (
            'id', 'title', 'destination_name', 'owner', 'start_date', 'end_date',
            'duration_days', 'status', 'budget_amount', 'currency',
            'collaborator_count', 'created_at',
        )
        read_only_fields = fields
        extra_kwargs = {
            'title': {'help_text': 'Short name for the trip.'},
            'start_date': {'help_text': 'First day of the trip.'},
            'end_date': {'help_text': 'Last day of the trip, inclusive.'},
            'budget_amount': {'help_text': 'Planned trip budget amount.'},
        }

    def get_duration_days(self, obj) -> int:
        """Return inclusive trip length."""
        return obj.duration_days

    def get_destination_name(self, obj) -> str:
        """Return the destination name or an empty value for an unassigned trip."""
        return obj.destination.name if obj.destination_id else ''

    def get_collaborator_count(self, obj) -> int:
        """Return the number of accepted collaborator records."""
        if hasattr(obj, 'collaborator_count'):
            return obj.collaborator_count
        return obj.collaborations.count()


class ItineraryDetailSerializer(ItineraryListSerializer):
    """Detailed itinerary response with nested days and collaborators."""

    daily_plans = DailyPlanSerializer(many=True, read_only=True)
    collaborations = CollaborationSerializer(many=True, read_only=True)

    class Meta(ItineraryListSerializer.Meta):
        fields = ItineraryListSerializer.Meta.fields + (
            'description', 'destination', 'daily_plans', 'collaborations',
            'itinerary_pdf', 'updated_at',
        )
        read_only_fields = fields

    def to_representation(self, instance):
        """Return the full nested representation used for detail responses."""
        return super().to_representation(instance)


class ItineraryWriteSerializer(serializers.ModelSerializer):
    """Create or update an itinerary while keeping ownership server-controlled."""

    destination_id = serializers.PrimaryKeyRelatedField(
        source='destination', queryset=Itinerary._meta.get_field('destination').remote_field.model.objects.all(),
        required=False, allow_null=True,
        help_text='Optional destination primary key for this trip.',
    )

    class Meta:
        model = Itinerary
        fields = (
            'id', 'destination_id', 'title', 'description', 'start_date', 'end_date',
            'status', 'budget_amount', 'currency', 'itinerary_pdf',
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'status': {'help_text': 'Current planning, booked, or completed state.'},
            'itinerary_pdf': {'help_text': 'Optional itinerary PDF document.'},
            'currency': {'help_text': 'Three-letter currency code for trip amounts.'},
        }

    def validate(self, attrs):
        """Validate a coherent date range and a non-negative budget."""
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        budget = attrs.get('budget_amount', getattr(self.instance, 'budget_amount', 0))
        errors = {}
        if start and end and end < start:
            errors['end_date'] = 'End date cannot be before start date.'
        if budget < 0:
            errors['budget_amount'] = 'Budget cannot be negative.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def validate_start_date(self, value):
        """Require a real date value from the serializer's date parser."""
        return value

    def create(self, validated_data):
        """Create a trip owned by the authenticated request user."""
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            raise serializers.ValidationError('An authenticated owner is required.')
        owner = validated_data.pop('owner', request.user)
        return Itinerary.objects.create(owner=owner, **validated_data)

    def update(self, instance, validated_data):
        """Apply validated changes while preserving the existing owner."""
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class ItineraryPDFUploadSerializer(serializers.ModelSerializer):
    """Validate an itinerary PDF upload and update its document field."""

    class Meta:
        model = Itinerary
        fields = ('itinerary_pdf',)

    def validate_itinerary_pdf(self, value):
        """Check file size, filename extension, MIME type, and PDF signature."""
        return validate_pdf_upload(value)


class ActivityLogSerializer(serializers.ModelSerializer):
    """Read-only representation of an itinerary audit event."""

    actor = UserSummarySerializer(read_only=True)

    class Meta:
        model = ActivityLog
        fields = ('id', 'itinerary', 'actor', 'action', 'details', 'created_at')
        read_only_fields = fields


class ItinerarySearchParamsSerializer(serializers.Serializer):
    """Document supported trip search query and body parameters."""

    search = serializers.CharField(required=False, help_text='Search trip titles and descriptions.')
    status = serializers.ChoiceField(choices=Itinerary.Status.choices, required=False)
    owner = serializers.IntegerField(required=False)
    destination_id = serializers.IntegerField(required=False)
    starts_after = serializers.DateField(required=False)
    starts_before = serializers.DateField(required=False)
    ordering = serializers.CharField(required=False)


class ItinerarySearchPageSerializer(serializers.Serializer):
    """Document paginated itinerary search results."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ItineraryListSerializer(many=True)


class BookingBulkUpdateItemSerializer(serializers.Serializer):
    """Describe one requested booking status change."""

    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=Booking.Status.choices)


class BookingBulkUpdateRequestSerializer(serializers.Serializer):
    """Describe the list accepted by the bulk booking endpoint."""

    bookings = BookingBulkUpdateItemSerializer(many=True)


class BookingBulkResultSerializer(serializers.Serializer):
    """Describe one success or failure entry returned by a bulk update."""

    id = serializers.IntegerField(allow_null=True)
    success = serializers.BooleanField()
    status = serializers.ChoiceField(choices=Booking.Status.choices, required=False)
    error = serializers.CharField(required=False)


class BookingBulkUpdateResponseSerializer(serializers.Serializer):
    """Describe aggregated bulk update results."""

    success_count = serializers.IntegerField()
    failure_count = serializers.IntegerField()
    results = BookingBulkResultSerializer(many=True)


class TripReportBookingSerializer(serializers.Serializer):
    """Summarize booking totals in a trip report."""

    count = serializers.IntegerField()
    total_price = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_count = serializers.IntegerField()


class TripReportBudgetSerializer(serializers.Serializer):
    """Summarize planned and recorded spend in a trip report."""

    planned = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
    spent = serializers.DecimalField(max_digits=14, decimal_places=2)


class TripReportSerializer(serializers.Serializer):
    """Document the combined itinerary, booking, and budget report response."""

    itinerary = ItineraryDetailSerializer()
    daily_plans = DailyPlanSerializer(many=True)
    bookings = TripReportBookingSerializer()
    budget = TripReportBudgetSerializer()


class TripAnalyticsSummarySerializer(serializers.Serializer):
    """Document high-level user itinerary analytics."""

    itinerary_count = serializers.IntegerField()
    total_planned_budget = serializers.DecimalField(max_digits=16, decimal_places=2)
    planning_count = serializers.IntegerField()
    booked_count = serializers.IntegerField()


class TripBudgetSummarySerializer(serializers.Serializer):
    """Document the aggregated trip budget response."""

    total_budget = serializers.DecimalField(max_digits=16, decimal_places=2)
    total_spent = serializers.DecimalField(max_digits=16, decimal_places=2)
    total_remaining = serializers.DecimalField(max_digits=16, decimal_places=2)
