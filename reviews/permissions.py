"""Object access rules for user-submitted reviews."""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class ReviewOwnerOrReadOnly(BasePermission):
    """Allow public reads while limiting changes to the review author."""

    message = 'Only the review author can change or remove this review.'

    def has_permission(self, request, view):
        """Allow safe requests and require authentication for review writes."""
        return request.method in SAFE_METHODS or bool(
            request.user and request.user.is_authenticated,
        )

    def has_object_permission(self, request, view, obj):
        """Allow safe reads or writes by the review's author."""
        return request.method in SAFE_METHODS or obj.user_id == request.user.pk
