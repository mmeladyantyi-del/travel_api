from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from budgets.models import Budget, Expense
from destinations.models import Destination
from itineraries.models import Itinerary


class BudgetApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='planner', email='planner@example.com', password='StrongPass123!')
        self.destination = Destination.objects.create(name='Durban', slug='durban', country='South Africa')
        self.trip = Itinerary.objects.create(owner=self.user, destination=self.destination, title='Beach trip', start_date=date(2026, 11, 1), end_date=date(2026, 11, 4))
        self.client.force_authenticate(self.user)

    def test_owner_can_create_budget(self):
        response = self.client.post(reverse('api_v1:budget-list'), {'itinerary': self.trip.pk, 'total_amount': '5000.00', 'currency': 'ZAR'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Budget.objects.get().itinerary, self.trip)

    def test_budget_reports_spent_and_remaining(self):
        budget = Budget.objects.create(itinerary=self.trip, total_amount='5000.00')
        Expense.objects.create(budget=budget, description='Lunch', amount='250.00', spent_on=date(2026, 11, 2))
        response = self.client.get(reverse('api_v1:budget-detail', args=[budget.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data['spent_amount']), Decimal('250.00'))
        self.assertEqual(Decimal(response.data['remaining_amount']), Decimal('4750.00'))

    def test_owner_can_add_expense(self):
        budget = Budget.objects.create(itinerary=self.trip, total_amount='5000.00')
        response = self.client.post(reverse('api_v1:expense-list'), {'budget': budget.pk, 'description': 'Lunch', 'amount': '250.00', 'spent_on': '2026-11-02'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Expense.objects.count(), 1)

    def test_expense_rejects_nonpositive_amount(self):
        budget = Budget.objects.create(itinerary=self.trip, total_amount='5000.00')
        response = self.client.post(reverse('api_v1:expense-list'), {'budget': budget.pk, 'description': 'Lunch', 'amount': '0', 'spent_on': '2026-11-02'}, format='json')
        self.assertEqual(response.status_code, 400)
