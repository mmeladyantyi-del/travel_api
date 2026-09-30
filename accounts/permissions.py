"""Permissions shared by account and booking endpoints."""

from rest_framework.permissions import BasePermission


class IsBookingOwner(BasePermission):
    """Allow users to access only bookings that belong to them."""

    message = 'You can only access your own bookings.'

    def has_permission(self, request, view):
        """Require authentication before applying the booking ownership rule."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        """Compare the booking owner with the authenticated request user."""
        booking_user_id = getattr(obj, 'user_id', None)
        return booking_user_id == request.user.pk
