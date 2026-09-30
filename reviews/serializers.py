"""Serializers for review submissions and review display."""

from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    """Read or write a review while keeping reviewer identity server-controlled."""

    user = UserSummarySerializer(read_only=True)
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            'id', 'user', 'destination', 'activity', 'target_name', 'rating',
            'title', 'body', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'user', 'target_name', 'created_at', 'updated_at')
        extra_kwargs = {
            'rating': {'help_text': 'Whole-number rating from one to five.'},
            'destination': {'help_text': 'Set when reviewing a destination.'},
            'activity': {'help_text': 'Set when reviewing an activity.'},
        }

    def get_target_name(self, obj) -> str | None:
        """Return the name of the reviewed destination or activity."""
        target = obj.destination or obj.activity
        return target.name if target else None

    def validate_rating(self, value):
        """Enforce the public one-to-five rating scale."""
        if not 1 <= value <= 5:
            raise serializers.ValidationError('Rating must be between one and five.')
        return value

    def validate(self, attrs):
        """Require exactly one review target, including for partial updates."""
        destination = attrs.get('destination', getattr(self.instance, 'destination', None))
        activity = attrs.get('activity', getattr(self.instance, 'activity', None))
        if bool(destination) == bool(activity):
            raise serializers.ValidationError('Select exactly one destination or activity.')
        return attrs

    def create(self, validated_data):
        """Create a review for the authenticated user."""
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            raise serializers.ValidationError('An authenticated reviewer is required.')
        user = validated_data.pop('user', request.user)
        return Review.objects.create(user=user, **validated_data)
