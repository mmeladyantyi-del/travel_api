from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from destinations.models import Destination
from reviews.models import Review


class ReviewApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='reviewer', email='reviewer@example.com', password='StrongPass123!')
        self.destination = Destination.objects.create(name='Pretoria', slug='pretoria', country='South Africa')

    def test_reviews_are_publicly_listable(self):
        Review.objects.create(user=self.user, destination=self.destination, rating=5, title='Great visit')
        response = self.client.get(reverse('api_v1:review-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_anonymous_user_cannot_create_review(self):
        response = self.client.post(reverse('api_v1:review-list'), {'destination': self.destination.pk, 'rating': 5}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_authenticated_user_can_create_review(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('api_v1:review-list'), {'destination': self.destination.pk, 'rating': 5, 'title': 'Great visit'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Review.objects.get().user, self.user)

    def test_review_requires_exactly_one_target(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('api_v1:review-list'), {'rating': 5}, format='json')
        self.assertEqual(response.status_code, 400)
