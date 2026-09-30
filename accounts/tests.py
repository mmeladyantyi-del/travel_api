"""Account model and authentication API tests."""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class UserModelTests(APITestCase):
    """Cover custom user creation and public display behavior."""

    def test_user_string_uses_full_name(self):
        user = User.objects.create_user(username='traveler', email='traveler@example.com', password='Strong-pass-2026!', first_name='Ada', last_name='Lovelace')
        self.assertEqual(str(user), 'Ada Lovelace')

    def test_user_string_falls_back_to_username(self):
        user = User.objects.create_user(username='solo', email='solo@example.com', password='Strong-pass-2026!')
        self.assertEqual(str(user), 'solo')

    def test_user_default_currency(self):
        user = User.objects.create_user(username='currency', email='currency@example.com', password='Strong-pass-2026!')
        self.assertEqual(user.preferred_currency, 'ZAR')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthenticationApiTests(APITestCase):
    """Exercise registration, JWT, profile, and password recovery endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username='jane', email='jane@example.com', password='Initial-Password-927!', first_name='Jane')
        self.client.defaults['HTTP_HOST'] = 'localhost'

    def test_register_returns_created_and_hashes_password(self):
        response = self.client.post(reverse('accounts:register'), {'username': 'new-traveler', 'email': 'new@example.com', 'password': 'Canyon-Sunset-820!River'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(username='new-traveler')
        self.assertTrue(created.check_password('Canyon-Sunset-820!River'))
        self.assertNotIn('password', response.data)

    def test_register_rejects_duplicate_email(self):
        response = self.client.post(reverse('accounts:register'), {'username': 'duplicate', 'email': 'JANE@example.com', 'password': 'Canyon-Sunset-820!River'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_weak_password(self):
        response = self.client.post(reverse('accounts:register'), {'username': 'weak', 'email': 'weak@example.com', 'password': 'password'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_by_username_returns_200_and_jwt_pair(self):
        response = self.client.post(reverse('accounts:login'), {'identifier': 'jane', 'password': 'Initial-Password-927!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['username'], 'jane')

    def test_login_by_email_returns_200(self):
        response = self.client.post(reverse('accounts:login'), {'identifier': 'JANE@example.com', 'password': 'Initial-Password-927!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_login_uses_structured_error_response(self):
        response = self.client.post(reverse('accounts:login'), {'identifier': 'jane', 'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'validation_error')

    def test_refresh_returns_new_access_token(self):
        login = self.client.post(reverse('accounts:login'), {'identifier': 'jane', 'password': 'Initial-Password-927!'}, format='json')
        response = self.client.post(reverse('accounts:token-refresh'), {'refresh': login.data['refresh']}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['error']['code'], 'authentication_required')

    def test_profile_can_be_retrieved_and_updated(self):
        self.client.force_authenticate(self.user)
        profile_url = reverse('accounts:profile')
        self.assertEqual(self.client.get(profile_url).status_code, status.HTTP_200_OK)
        response = self.client.patch(profile_url, {'preferred_currency': 'EUR'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_currency, 'EUR')

    def test_password_change_requires_current_password(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('accounts:password-change'), {'old_password': 'wrong', 'new_password': 'Lake-Trail-2026!Bright', 'confirm_password': 'Lake-Trail-2026!Bright'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_change_persists_new_password(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('accounts:password-change'), {'old_password': 'Initial-Password-927!', 'new_password': 'Lake-Trail-2026!Bright', 'confirm_password': 'Lake-Trail-2026!Bright'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Lake-Trail-2026!Bright'))

    def test_password_reset_request_does_not_disclose_account_existence(self):
        url = reverse('accounts:password-reset-request')
        existing = self.client.post(url, {'email': 'jane@example.com'}, format='json')
        missing = self.client.post(url, {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(existing.status_code, status.HTTP_200_OK)
        self.assertEqual(existing.data, missing.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_confirm_updates_password_and_token_is_one_time(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse('accounts:password-reset-confirm', kwargs={'uidb64': uid, 'token': token})
        payload = {'new_password': 'Coastal-Path-2026!Tide', 'confirm_password': 'Coastal-Path-2026!Tide'}
        first = self.client.post(url, payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(payload['new_password']))
        second = self.client.post(url, payload, format='json')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
