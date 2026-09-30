"""Serializers for account registration and profile data."""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    """Compact public representation for nested account references."""

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'display_name')
        read_only_fields = fields

    def get_display_name(self, obj) -> str:
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
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def create(self, validated_data):
        """Create the account with a properly hashed password."""
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """Authenticate a user by username or email and issue a JWT pair."""

    identifier = serializers.CharField(help_text='Account username or email address.')
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Verify credentials and return signed access and refresh tokens."""
        identifier = attrs['identifier'].strip()
        user = User.objects.filter(username__iexact=identifier).first()
        if user is None:
            user = User.objects.filter(email__iexact=identifier).first()
        authenticated_user = None
        if user is not None:
            authenticated_user = authenticate(
                request=self.context.get('request'),
                username=user.username,
                password=attrs['password'],
            )
        if authenticated_user is None:
            raise serializers.ValidationError('Invalid username/email or password.')
        refresh = RefreshToken.for_user(authenticated_user)
        return {
            'user': authenticated_user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class LoginResponseSerializer(serializers.Serializer):
    """Document the login token response and safe user profile."""

    user = UserSummarySerializer()
    refresh = serializers.CharField()
    access = serializers.CharField()


class MessageResponseSerializer(serializers.Serializer):
    """Document generic account-operation status messages."""

    detail = serializers.CharField()


class PasswordChangeSerializer(serializers.Serializer):
    """Validate current and new passwords for an authenticated user."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        """Require the current password to match the signed-in account."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate_new_password(self, value):
        """Apply the configured Django password validators."""
        try:
            validate_password(value, user=self.context['request'].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def validate(self, attrs):
        """Require matching confirmation and a changed password."""
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({'new_password': 'Choose a different password.'})
        return attrs

    def save(self, **kwargs):
        """Set and save the new password hash for the current account."""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    """Normalize the email used to request password recovery."""

    email = serializers.EmailField()

    def validate_email(self, value):
        """Normalize email casing before account lookup."""
        return value.lower()


class PasswordResetConfirmRequestSerializer(serializers.Serializer):
    """Describe the new password fields accepted alongside path tokens."""

    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Validate a one-time reset token and the replacement password."""

    uidb64 = serializers.CharField(write_only=True)
    token = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Resolve the user and verify the signed reset token."""
        try:
            user_id = force_str(urlsafe_base64_decode(attrs['uidb64']))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, DjangoValidationError, User.DoesNotExist):
            raise serializers.ValidationError({'token': 'This password reset link is invalid or expired.'})
        from django.contrib.auth.tokens import default_token_generator
        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'token': 'This password reset link is invalid or expired.'})
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        try:
            validate_password(attrs['new_password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.messages}) from exc
        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        """Save the replacement password and invalidate this reset token."""
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user
