from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from bookings.models import Booking
from destinations.models import Accommodation, Destination


class BookingModelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='booker', email='booker@example.com', password='StrongPass123!')
        self.destination = Destination.objects.create(name='Cape Town', country='South Africa', description='Coast')
        self.stay = Accommodation.objects.create(destination=self.destination, name='Harbour Hotel', description='Central', nightly_rate='1200.00')

    def test_requires_exactly_one_resource(self):
        booking = Booking(user=self.user, start_date=date.today(), total_price=100)
        with self.assertRaises(ValidationError):
            booking.full_clean()

    def test_rejects_reversed_date_range(self):
        booking = Booking(user=self.user, accommodation=self.stay, start_date=date.today(), end_date=date.today() - timedelta(days=1), total_price=100)
        with self.assertRaises(ValidationError):
            booking.full_clean()

    def test_confirm_persists_status(self):
        booking = Booking.objects.create(user=self.user, accommodation=self.stay, start_date=date.today(), total_price=100)
        booking.confirm()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_string_representation(self):
        booking = Booking.objects.create(user=self.user, accommodation=self.stay, start_date=date.today(), total_price=100)
        self.assertIn('pending', str(booking))


class BookingApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='booker', email='booker@example.com', password='StrongPass123!')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='StrongPass123!')
        self.destination = Destination.objects.create(name='Cape Town', country='South Africa', description='Coast')
        self.stay = Accommodation.objects.create(destination=self.destination, name='Harbour Hotel', description='Central', nightly_rate='1200.00')
        self.client.force_authenticate(self.user)

    def payload(self):
        return {'accommodation': self.stay.pk, 'start_date': str(date.today()), 'total_price': '100.00'}

    def create_booking(self):
        return Booking.objects.create(user=self.user, accommodation=self.stay, start_date=date.today(), total_price=100)

    def test_create_booking_assigns_current_user(self):
        response = self.client.post(reverse('api_v1:booking-list'), self.payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.get().user, self.user)

    def test_create_rejects_missing_resource(self):
        response = self.client.post(reverse('api_v1:booking-list'), {'start_date': str(date.today()), 'total_price': '100'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_confirm_action(self):
        booking = self.create_booking()
        response = self.client.post(reverse('api_v1:booking-confirm', args=[booking.pk]))
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_cancel_action(self):
        booking = self.create_booking()
        response = self.client.post(reverse('api_v1:booking-cancel', args=[booking.pk]))
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_other_user_cannot_retrieve(self):
        booking = self.create_booking()
        self.client.force_authenticate(self.other)
        response = self.client.get(reverse('api_v1:booking-detail', args=[booking.pk]))
        self.assertEqual(response.status_code, 404)
