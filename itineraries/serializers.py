"""Serializers for trip plans, collaboration, and scheduled days."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from destinations.models import Activity
from destinations.serializers import ActivitySerializer
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

    def get_duration_days(self, obj):
        """Return inclusive trip length."""
        return obj.duration_days

    def get_destination_name(self, obj):
        """Return the destination name or an empty value for an unassigned trip."""
        return obj.destination.name if obj.destination_id else ''

    def get_collaborator_count(self, obj):
        """Return the number of accepted collaborator records."""
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
        return Itinerary.objects.create(owner=request.user, **validated_data)

    def update(self, instance, validated_data):
        """Apply validated changes while preserving the existing owner."""
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class ActivityLogSerializer(serializers.ModelSerializer):
    """Read-only representation of an itinerary audit event."""

    actor = UserSummarySerializer(read_only=True)

    class Meta:
        model = ActivityLog
        fields = ('id', 'itinerary', 'actor', 'action', 'details', 'created_at')
        read_only_fields = fields
