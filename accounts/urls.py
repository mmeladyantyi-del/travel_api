"""Authentication and account profile routes."""

from django.urls import path

from .views import (
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    RegistrationView,
    TokenRefreshEndpoint,
)

app_name = 'accounts'

urlpatterns = [
    path('register/', RegistrationView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshEndpoint.as_view(), name='token-refresh'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path(
        'password/reset/confirm/<str:uidb64>/<str:token>/',
        PasswordResetConfirmView.as_view(), name='password-reset-confirm',
    ),
]
