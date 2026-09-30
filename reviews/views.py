"""Review resource endpoints."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Review
from .permissions import ReviewOwnerOrReadOnly
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    """Browse reviews and allow authenticated users to manage their own."""

    queryset = Review.objects.none()
    serializer_class = ReviewSerializer
    permission_classes = [ReviewOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['destination', 'activity', 'rating']
    search_fields = ['title', 'body', 'destination__name', 'activity__name']
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']

    def get_queryset(self):
        """Preload reviewer and target data for nested review representations."""
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return Review.objects.select_related('user', 'destination', 'activity')

    def get_permissions(self):
        """Require login for writes while preserving public review reads."""
        permissions = [ReviewOwnerOrReadOnly()]
        if self.action in {'create'}:
            permissions.append(IsAuthenticated())
        return permissions

    def perform_create(self, serializer):
        """Attach the authenticated user as the review author."""
        serializer.save(user=self.request.user)
