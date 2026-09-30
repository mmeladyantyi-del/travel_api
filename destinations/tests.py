"""Destination catalog, filter, serializer, and upload tests."""

from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from .filters import DestinationFilter
from .models import Accommodation, Activity, Destination
from .serializers import DestinationDetailSerializer, DestinationWriteSerializer

User = get_user_model()


def make_png():
    """Create a tiny valid PNG for upload validation."""
    output = BytesIO()
    Image.new('RGB', (2, 2), color='blue').save(output, format='PNG')
    return output.getvalue()


class DestinationModelTests(TestCase):
    """Check catalog model labels and reverse relationships."""

    def setUp(self):
        self.destination = Destination.objects.create(
            name='Cape Town', slug='cape-town', country='South Africa',
        )

    def test_destination_string_contains_country(self):
        self.assertEqual(str(self.destination), 'Cape Town, South Africa')

    def test_activity_and_accommodation_relations(self):
        activity = Activity.objects.create(destination=self.destination, name='Hike')
        stay = Accommodation.objects.create(
            destination=self.destination, name='Harbor Hotel', nightly_rate='120.00',
        )
        self.assertEqual(self.destination.activities.get(), activity)
        self.assertEqual(self.destination.accommodations.get(), stay)
        self.assertIn('Cape Town', str(activity))
        self.assertIn('Cape Town', str(stay))


class DestinationSerializerAndFilterTests(TestCase):
    """Exercise catalog serializer validation and filtered results."""

    def setUp(self):
        self.destination = Destination.objects.create(
            name='Cape Town', slug='cape-town', country='South Africa',
            category='coastal', climate='mediterranean',
        )
        Activity.objects.create(destination=self.destination, name='Hike')
        Accommodation.objects.create(
            destination=self.destination, name='Harbor Hotel', nightly_rate='120.00',
        )
        self.other = Destination.objects.create(
            name='Reykjavik', slug='reykjavik', country='Iceland', category='city',
        )

    def test_filterset_matches_case_insensitive_country(self):
        results = DestinationFilter(data={'country': 'south'}, queryset=Destination.objects.all()).qs
        self.assertEqual(list(results), [self.destination])

    def test_detail_serializer_includes_nested_resources_and_counts(self):
        data = DestinationDetailSerializer(self.destination).data
        self.assertEqual(data['activity_count'], 1)
        self.assertEqual(data['accommodation_count'], 1)
        self.assertEqual(data['activities'][0]['name'], 'Hike')

    def test_write_serializer_trims_name_and_country(self):
        serializer = DestinationWriteSerializer(data={
            'name': '  Durban  ', 'slug': 'durban', 'country': '  South Africa ',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['name'], 'Durban')
        self.assertEqual(serializer.validated_data['country'], 'South Africa')

    def test_write_serializer_rejects_duplicate_name(self):
        serializer = DestinationWriteSerializer(data={
            'name': ' cape town ', 'slug': 'cape-town-2', 'country': 'South Africa',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('name', serializer.errors)


class DestinationApiTests(TestCase):
    """Check public search and protected photo uploads."""

    def setUp(self):
        self.destination = Destination.objects.create(
            name='Cape Town', slug='cape-town', country='South Africa',
        )
        self.client = APIClient()

    def test_search_endpoint_returns_matching_destination(self):
        response = self.client.get(reverse('destinations:search'), {'search': 'cape'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['name'], 'Cape Town')

    def test_photo_upload_rejects_non_staff_user(self):
        user = User.objects.create_user(
            username='traveler', email='traveler@example.com', password='Strong-pass-2026!',
        )
        self.client.force_authenticate(user)
        upload = SimpleUploadedFile('image.png', make_png(), content_type='image/png')
        response = self.client.post(
            reverse('destinations:upload-photo', kwargs={'pk': self.destination.pk}),
            {'primary_photo': upload}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_upload_valid_destination_photo(self):
        staff = User.objects.create_superuser(
            username='editor', email='editor@example.com', password='Strong-pass-2026!',
        )
        self.client.force_authenticate(staff)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            upload = SimpleUploadedFile('cape.png', make_png(), content_type='image/png')
            response = self.client.post(
                reverse('destinations:upload-photo', kwargs={'pk': self.destination.pk}),
                {'primary_photo': upload}, format='multipart',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.destination.refresh_from_db()
            self.assertTrue(self.destination.primary_photo.name.endswith('.png'))

    def test_staff_photo_upload_rejects_invalid_image(self):
        staff = User.objects.create_superuser(
            username='editor', email='editor@example.com', password='Strong-pass-2026!',
        )
        self.client.force_authenticate(staff)
        upload = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')
        response = self.client.post(
            reverse('destinations:upload-photo', kwargs={'pk': self.destination.pk}),
            {'primary_photo': upload}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
