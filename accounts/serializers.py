"""Serializers for account registration and profile data."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    """Compact public representation for nested account references."""

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'display_name')
        read_only_fields = fields

    def get_display_name(self, obj):
        """Return the full name or username for display."""
        return obj.get_full_name() or obj.username


class UserProfileSerializer(UserSummarySerializer):
    """Serializer for reading and updating the current user's profile."""

    class Meta(UserSummarySerializer.Meta):
        fields = (
            'id', 'username', 'display_name', 'first_name', 'last_name',
            'email', 'phone_number', 'preferred_currency', 'created_at',
        )
        read_only_fields = ('id', 'username', 'display_name', 'created_at')
        extra_kwargs = {
            'email': {'help_text': 'Unique email address for account communication.'},
            'phone_number': {'help_text': 'Optional contact number.'},
            'preferred_currency': {'help_text': 'Three-letter currency code.'},
        }


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Validate registration fields and hash the password on creation."""

    password = serializers.CharField(
        write_only=True, min_length=8,
        help_text='Password with at least eight characters; never returned by the API.',
    )

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'first_name', 'last_name')
        read_only_fields = ('id',)
        extra_kwargs = {
            'email': {'help_text': 'A unique address for account communication.'},
            'username': {'help_text': 'Unique account name used to sign in.'},
        }

    def validate_email(self, value):
        """Reject email addresses already attached to an account."""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value.lower()

    def validate_password(self, value):
        """Apply Django's configured password-strength validators."""
        validate_password(value)
        return value

    def create(self, validated_data):
        """Create the account with a properly hashed password."""
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
