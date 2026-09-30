"""Itinerary models, permissions, and API tests."""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from .models import ActivityLog, Collaboration, DailyPlan, Itinerary
from .permissions import CanEditItinerary, IsTripOwner, IsTripOwnerOrCollaborator

User = get_user_model()


class ItineraryModelTests(TestCase):
    """Check trip dates and related-model behavior."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='Strong-pass-2026!',
        )
        self.trip = Itinerary.objects.create(
            owner=self.owner, title='Portugal',
            start_date=date(2027, 5, 1), end_date=date(2027, 5, 3),
        )

    def test_duration_is_inclusive(self):
        self.assertEqual(self.trip.duration_days, 3)

    def test_invalid_date_range_is_rejected(self):
        self.trip.end_date = date(2027, 4, 30)
        with self.assertRaises(ValidationError):
            self.trip.clean()

    def test_daily_plan_must_be_within_trip(self):
        plan = DailyPlan(itinerary=self.trip, day_number=1, date=date(2027, 4, 30))
        with self.assertRaises(ValidationError):
            plan.clean()

    def test_collaboration_and_activity_log(self):
        editor = User.objects.create_user(
            username='editor', email='editor@example.com', password='Strong-pass-2026!',
        )
        Collaboration.objects.create(
            itinerary=self.trip, user=editor, role=Collaboration.Role.EDITOR,
        )
        event = ActivityLog.objects.create(
            itinerary=self.trip, actor=editor, action=ActivityLog.Action.SHARED,
        )
        self.assertEqual(self.trip.collaborators.get(), editor)
        self.assertIn('shared', str(event))


class ItineraryPermissionTests(TestCase):
    """Check owner, collaborator, and editor/viewer access rules."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='Strong-pass-2026!',
        )
        self.editor = User.objects.create_user(
            username='editor', email='editor@example.com', password='Strong-pass-2026!',
        )
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@example.com', password='Strong-pass-2026!',
        )
        self.trip = Itinerary.objects.create(
            owner=self.owner, title='Weekend',
            start_date=date(2027, 1, 1), end_date=date(2027, 1, 2),
        )
        Collaboration.objects.create(
            itinerary=self.trip, user=self.editor, role=Collaboration.Role.EDITOR,
        )
        Collaboration.objects.create(
            itinerary=self.trip, user=self.viewer, role=Collaboration.Role.VIEWER,
        )
        self.factory = APIRequestFactory()

    def test_owner_can_edit_and_nonowner_is_denied(self):
        permission = IsTripOwner()
        request = self.factory.patch('/')
        request.user = self.owner
        self.assertTrue(permission.has_object_permission(request, None, self.trip))
        request.user = self.viewer
        self.assertFalse(permission.has_object_permission(request, None, self.trip))

    def test_viewer_read_only_and_editor_can_write(self):
        permission = CanEditItinerary()
        request = self.factory.get('/')
        request.user = self.viewer
        self.assertTrue(permission.has_object_permission(request, None, self.trip))
        request = self.factory.patch('/')
        request.user = self.viewer
        self.assertFalse(permission.has_object_permission(request, None, self.trip))
        request.user = self.editor
        self.assertTrue(permission.has_object_permission(request, None, self.trip))

    def test_collaborator_permission_accepts_viewer(self):
        request = self.factory.get('/')
        request.user = self.viewer
        self.assertTrue(
            IsTripOwnerOrCollaborator().has_object_permission(request, None, self.trip),
        )


class ItineraryApiTests(TestCase):
    """Exercise trip CRUD, search, collaboration, reporting, and duplication."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='Strong-pass-2026!',
        )
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@example.com', password='Strong-pass-2026!',
        )
        self.trip = Itinerary.objects.create(
            owner=self.owner, title='Weekend Lisbon',
            start_date=date(2027, 5, 1), end_date=date(2027, 5, 3),
        )
        self.client = APIClient()

    def test_list_requires_authentication(self):
        response = self.client.get(reverse('api_v1:itinerary-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_create_trip(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse('api_v1:itinerary-list'), {
            'title': 'Garden Route', 'start_date': '2027-06-01',
            'end_date': '2027-06-04', 'budget_amount': '1000.00',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.owner.itineraries.count(), 2)

    def test_reversed_dates_are_rejected(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse('api_v1:itinerary-list'), {
            'title': 'Invalid', 'start_date': '2027-06-05', 'end_date': '2027-06-01',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_search_and_report_trip(self):
        self.client.force_authenticate(self.owner)
        search = self.client.get(reverse('itineraries:search'), {'search': 'Lisbon'})
        report = self.client.get(reverse(
            'itineraries:report', kwargs={'trip_id': self.trip.pk},
        ))
        self.assertEqual(search.status_code, status.HTTP_200_OK)
        self.assertEqual(search.data['count'], 1)
        self.assertEqual(report.status_code, status.HTTP_200_OK)

    def test_viewer_can_read_but_not_update_trip(self):
        Collaboration.objects.create(
            itinerary=self.trip, user=self.viewer, role=Collaboration.Role.VIEWER,
        )
        self.client.force_authenticate(self.viewer)
        url = reverse('itineraries:detail', kwargs={'pk': self.trip.pk})
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)
        response = self.client.patch(url, {'title': 'Changed'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_add_update_and_remove_collaborator(self):
        self.client.force_authenticate(self.owner)
        url = reverse('itineraries:collaboration', kwargs={'trip_id': self.trip.pk})
        created = self.client.post(url, {'user_id': self.viewer.pk, 'role': 'viewer'}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        updated = self.client.patch(url, {'user_id': self.viewer.pk, 'role': 'editor'}, format='json')
        self.assertEqual(updated.data['role'], 'editor')
        removed = self.client.delete(url, {'user_id': self.viewer.pk}, format='json')
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)

    def test_owner_can_duplicate_trip(self):
        self.client.force_authenticate(self.owner)
        url = reverse('api_v1:itinerary-duplicate', kwargs={'pk': self.trip.pk})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.owner.itineraries.count(), 2)
