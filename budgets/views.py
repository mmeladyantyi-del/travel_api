"""Budget and expense resource endpoints."""

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from itineraries.permissions import CanEditItinerary, IsTripOwnerOrCollaborator
from .filters import ExpenseFilter
from .models import Budget, Expense
from .serializers import BudgetSerializer, ExpenseSerializer


def _visible_budget_filter(user):
    """Return a query condition for trips owned by or shared with a user."""
    return Q(itinerary__owner=user) | Q(itinerary__collaborations__user=user)


class BudgetViewSet(viewsets.ModelViewSet):
    """Manage budgets only for trips visible to the current user."""

    queryset = Budget.objects.none()
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated, IsTripOwnerOrCollaborator, CanEditItinerary]

    def get_queryset(self):
        """Return visible budgets with trip relationships loaded."""
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return Budget.objects.filter(_visible_budget_filter(self.request.user)).select_related(
            'itinerary', 'itinerary__owner', 'itinerary__destination',
        ).prefetch_related('expenses')

    def perform_create(self, serializer):
        """Require edit permission on the selected itinerary before saving."""
        itinerary = serializer.validated_data['itinerary']
        # Create requests have no object yet, so enforce the same role rule explicitly.
        check = CanEditItinerary()
        if not check.has_object_permission(self.request, self, itinerary):
            raise PermissionDenied(check.message)
        serializer.save()


class ExpenseViewSet(viewsets.ModelViewSet):
    """Manage expenses for budgets attached to accessible itineraries."""

    queryset = Expense.objects.none()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated, IsTripOwnerOrCollaborator, CanEditItinerary]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ExpenseFilter
    ordering_fields = ['spent_on', 'amount', 'created_at']
    ordering = ['-spent_on']

    def get_queryset(self):
        """Limit expenses to accessible trips and preload budget ownership."""
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return Expense.objects.filter(
            Q(budget__itinerary__owner=self.request.user)
            | Q(budget__itinerary__collaborations__user=self.request.user)
        ).select_related('budget__itinerary', 'budget__itinerary__owner').distinct()

    def perform_create(self, serializer):
        """Require edit permission on the expense's itinerary before saving."""
        budget = serializer.validated_data['budget']
        check = CanEditItinerary()
        if not check.has_object_permission(self.request, self, budget.itinerary):
            raise PermissionDenied(check.message)
        serializer.save()

