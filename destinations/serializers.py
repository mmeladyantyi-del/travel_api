"""Serializers for destinations and their bookable resources."""

from django.db.models import Avg
from rest_framework import serializers

from travel_api.upload_validators import validate_image_upload
from .models import Accommodation, Activity, Destination


class ActivitySerializer(serializers.ModelSerializer):
    """Represent an activity with its destination identifier."""

    class Meta:
        model = Activity
        fields = (
            'id', 'destination', 'name', 'description', 'duration_minutes',
            'price', 'currency', 'is_active', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {
            'destination': {'help_text': 'Destination where the activity takes place.'},
            'duration_minutes': {'help_text': 'Typical activity duration in minutes.'},
            'price': {'help_text': 'Price per participant in the selected currency.'},
        }

    def validate_duration_minutes(self, value):
        """Require a positive activity duration."""
        if value < 1:
            raise serializers.ValidationError('Duration must be at least one minute.')
        return value


class AccommodationSerializer(serializers.ModelSerializer):
    """Represent a lodging option and its current availability."""

    class Meta:
        model = Accommodation
        fields = (
            'id', 'destination', 'name', 'description', 'address', 'nightly_rate',
            'currency', 'photo', 'is_active', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {
            'name': {'help_text': 'Public name of the accommodation.'},
            'nightly_rate': {'help_text': 'Cost per night in the selected currency.'},
            'photo': {'help_text': 'Optional accommodation photo upload.'},
        }

    def validate_nightly_rate(self, value):
        """Disallow negative accommodation rates."""
        if value < 0:
            raise serializers.ValidationError('Nightly rate cannot be negative.')
        return value


class DestinationListSerializer(serializers.ModelSerializer):
    """Compact destination card with related-resource counts."""

    activity_count = serializers.SerializerMethodField()
    accommodation_count = serializers.SerializerMethodField()

    class Meta:
        model = Destination
        fields = (
            'id', 'name', 'slug', 'country', 'category', 'climate',
            'primary_photo', 'average_rating', 'activity_count',
            'accommodation_count',
        )
        read_only_fields = ('id', 'average_rating', 'activity_count', 'accommodation_count')
        extra_kwargs = {
            'slug': {'help_text': 'Unique URL-friendly destination name.'},
            'country': {'help_text': 'Country where the destination is located.'},
            'primary_photo': {'help_text': 'Optional destination image upload.'},
        }

    def get_activity_count(self, obj) -> int:
        """Return the count of active activities at this destination."""
        # Search and list views annotate counts to avoid one query per result card.
        if hasattr(obj, 'active_activity_count'):
            return obj.active_activity_count
        return obj.activities.filter(is_active=True).count()

    def get_accommodation_count(self, obj) -> int:
        """Return the count of active accommodations at this destination."""
        if hasattr(obj, 'active_accommodation_count'):
            return obj.active_accommodation_count
        return obj.accommodations.filter(is_active=True).count()


class DestinationDetailSerializer(DestinationListSerializer):
    """Detailed destination response with nested activities and lodging."""

    activities = ActivitySerializer(many=True, read_only=True)
    accommodations = AccommodationSerializer(many=True, read_only=True)
    review_count = serializers.SerializerMethodField()
    computed_rating = serializers.SerializerMethodField()

    class Meta(DestinationListSerializer.Meta):
        fields = DestinationListSerializer.Meta.fields + (
            'description', 'activities', 'accommodations', 'review_count',
            'computed_rating', 'created_at', 'updated_at',
        )
        read_only_fields = DestinationListSerializer.Meta.read_only_fields + (
            'activities', 'accommodations', 'review_count', 'computed_rating',
            'created_at', 'updated_at',
        )

    def get_review_count(self, obj) -> int:
        """Return the number of submitted destination reviews."""
        if hasattr(obj, 'review_count'):
            return obj.review_count
        return obj.reviews.count()

    def get_computed_rating(self, obj) -> float | None:
        """Return the mean of submitted reviews when available."""
        if hasattr(obj, 'computed_rating'):
            return obj.computed_rating
        return obj.reviews.aggregate(value=Avg('rating'))['value']

    def to_representation(self, instance):
        """Use the inherited compact card shape as the detail response base."""
        representation = super().to_representation(instance)
        return representation


class DestinationWriteSerializer(serializers.ModelSerializer):
    """Create and update destination catalog entries."""

    class Meta:
        model = Destination
        fields = (
            'id', 'name', 'slug', 'country', 'category', 'climate',
            'description', 'primary_photo',
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'name': {'help_text': 'Name shown in destination search results.'},
            'description': {'help_text': 'Overview shown on destination detail pages.'},
        }

    def validate_name(self, value):
        """Strip whitespace and prevent duplicate destination names."""
        value = value.strip()
        matches = Destination.objects.filter(name__iexact=value)
        if self.instance:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError('A destination with this name already exists.')
        return value

    def validate(self, attrs):
        """Ensure destination records include a country."""
        country = attrs.get('country', getattr(self.instance, 'country', ''))
        if not country.strip():
            raise serializers.ValidationError({'country': 'Country is required.'})
        attrs['country'] = country.strip()
        return attrs

    def create(self, validated_data):
        """Create a destination after serializer-level normalization."""
        return Destination.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """Update only fields provided by the request."""
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class DestinationSearchParamsSerializer(serializers.Serializer):
    """Document supported destination search parameters."""

    search = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    country = serializers.CharField(required=False)
    category = serializers.CharField(required=False)
    climate = serializers.CharField(required=False)
    min_rating = serializers.DecimalField(max_digits=3, decimal_places=2, required=False)
    max_rating = serializers.DecimalField(max_digits=3, decimal_places=2, required=False)


class DestinationSearchPageSerializer(serializers.Serializer):
    """Document paginated destination search results."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = DestinationListSerializer(many=True)


class DestinationRecommendationQuerySerializer(serializers.Serializer):
    """Validate optional filters and result limits for recommendations."""

    country = serializers.CharField(required=False, max_length=100)
    category = serializers.CharField(required=False, max_length=60)
    climate = serializers.CharField(required=False, max_length=60)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class DestinationRecommendationSerializer(DestinationListSerializer):
    """Destination card with an affinity score and explanation."""

    recommendation_score = serializers.IntegerField(read_only=True)
    recommendation_reason = serializers.CharField(read_only=True)

    class Meta(DestinationListSerializer.Meta):
        fields = DestinationListSerializer.Meta.fields + (
            'recommendation_score', 'recommendation_reason',
        )


class DestinationRecommendationPageSerializer(serializers.Serializer):
    """Document the paginated personalized destination response."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = DestinationRecommendationSerializer(many=True)


class DestinationPhotoUploadSerializer(serializers.ModelSerializer):
    """Validate a destination photo upload and update its primary image."""

    class Meta:
        model = Destination
        fields = ('primary_photo',)

    def validate_primary_photo(self, value):
        """Check size, safe extension, MIME type, and decoded image format."""
        return validate_image_upload(value)
