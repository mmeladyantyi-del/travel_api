"""Authentication, profile, and password management endpoints."""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    MessageResponseSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetConfirmRequestSerializer,
    PasswordResetRequestSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    UserSummarySerializer,
)

User = get_user_model()


class RegistrationView(generics.CreateAPIView):
    """Register a user with a validated password and unique email."""

    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]


class LoginView(APIView):
    """Authenticate by username or email and return a JWT pair."""

    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses=LoginResponseSerializer)
    def post(self, request):
        """Return access and refresh tokens with a safe account summary."""
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        response_data = {
            'access': data['access'],
            'refresh': data['refresh'],
            'user': UserSummarySerializer(data['user']).data,
        }
        return Response(response_data, status=status.HTTP_200_OK)


class TokenRefreshEndpoint(TokenRefreshView):
    """Exchange a valid refresh token for a new access token."""

    permission_classes = [AllowAny]
    serializer_class = TokenRefreshSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    """Retrieve or update the authenticated user's own profile."""

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """Use the request user as the only accessible profile."""
        return self.request.user


class PasswordChangeView(APIView):
    """Change an authenticated user's password after verifying the old one."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        """Validate old/new passwords and persist a new password hash."""
        serializer = PasswordChangeSerializer(
            data=request.data, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Password changed successfully.'}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """Send a time-limited password reset link without exposing account existence."""

    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetRequestSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        """Send reset instructions when the email belongs to an active user."""
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data['email'], is_active=True,
        ).first()
        if user:
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_path = reverse(
                'accounts:password-reset-confirm',
                kwargs={'uidb64': uidb64, 'token': token},
            )
            reset_url = request.build_absolute_uri(reset_path)
            send_mail(
                subject='Travel API password reset',
                message=(
                    'Use this one-time link to reset your password:\n'
                    f'{reset_url}\n\n'
                    'If you did not request this change, you can ignore this message.'
                ),
                from_email=None,
                recipient_list=[user.email],
                fail_silently=False,
            )
        return Response(
            {'detail': 'If an active account exists for that email, reset instructions have been sent.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """Confirm a reset link and set a replacement password."""

    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetConfirmRequestSerializer, responses=MessageResponseSerializer)
    def post(self, request, uidb64, token):
        """Validate the path token and update the user's password."""
        payload = request.data.copy()
        payload['uidb64'] = uidb64
        payload['token'] = token
        serializer = PasswordResetConfirmSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)
