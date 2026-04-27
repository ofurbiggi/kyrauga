from django import forms
from django.test import TestCase
from django.utils import timezone

from wagtail.images.forms import get_image_form

from media_importer.models import CustomImage, DropboxAuthState


class DropboxAuthStateModelTests(TestCase):
    def test_get_solo_returns_usable_instance(self):
        auth_state = DropboxAuthState.get_solo()

        self.assertIsNotNone(auth_state.pk)
        self.assertEqual(DropboxAuthState.objects.count(), 1)

    def test_default_state_is_inactive(self):
        auth_state = DropboxAuthState.get_solo()

        self.assertFalse(auth_state.is_active)
        self.assertEqual(auth_state.refresh_token, "")

    def test_saving_auth_fields_works(self):
        auth_state = DropboxAuthState.get_solo()
        connected_at = timezone.now()
        auth_state.refresh_token = "refresh-token"
        auth_state.connected_account_id = "dbid:123"
        auth_state.connected_email = "user@example.com"
        auth_state.connected_name = "Example User"
        auth_state.is_active = True
        auth_state.connected_at = connected_at
        auth_state.save()

        refreshed = DropboxAuthState.get_solo()
        self.assertEqual(refreshed.refresh_token, "refresh-token")
        self.assertEqual(refreshed.connected_email, "user@example.com")
        self.assertEqual(refreshed.connected_name, "Example User")
        self.assertTrue(refreshed.is_active)
        self.assertEqual(refreshed.connected_at, connected_at)


class CustomImageFormTests(TestCase):
    def test_description_uses_textarea_widget(self):
        form_class = get_image_form(CustomImage)
        form = form_class()

        self.assertIsInstance(form.fields["description"].widget, forms.Textarea)

    def test_metadata_fields_are_available_on_custom_image_form(self):
        form_class = get_image_form(CustomImage)
        form = form_class()

        for field_name in CustomImage.metadata_field_names:
            self.assertIn(field_name, form.fields)
