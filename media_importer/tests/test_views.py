from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from media_importer.models import DropboxAuthState
from media_importer.services.dropbox_oauth import DropboxOAuthError


@override_settings(
    DROPBOX_APP_KEY="app-key",
    DROPBOX_APP_SECRET="app-secret",
    DROPBOX_REDIRECT_URI="http://127.0.0.1:8000/admin/dropbox-import/oauth/callback/",
    DROPBOX_TO_PUBLISH_FOLDER="/to-publish",
    DROPBOX_PUBLISHED_FOLDER="/published",
)
class DropboxOAuthViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.user)

    @patch("media_importer.views.build_authorize_url", return_value="https://www.dropbox.com/oauth2/authorize?client_id=app-key")
    def test_oauth_start_redirects_to_dropbox(self, mock_build_authorize_url):
        response = self.client.get(reverse("dropbox_oauth_start"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://www.dropbox.com/oauth2/authorize?client_id=app-key")
        mock_build_authorize_url.assert_called_once()

    @patch("media_importer.views.DropboxOAuthCallbackView._fetch_account_info")
    @patch("media_importer.views.exchange_code_for_tokens")
    def test_oauth_callback_stores_refresh_token_and_adds_success_message(
        self,
        mock_exchange_code_for_tokens,
        mock_fetch_account_info,
    ):
        mock_exchange_code_for_tokens.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "account_id": "dbid:123",
            "expires_in": 14400,
        }
        mock_fetch_account_info.return_value = {
            "account_id": "dbid:123",
            "email": "user@example.com",
            "name": "Example User",
        }

        response = self.client.get(reverse("dropbox_oauth_callback"), {"code": "oauth-code"}, follow=True)

        auth_state = DropboxAuthState.get_solo()
        self.assertTrue(auth_state.is_active)
        self.assertEqual(auth_state.refresh_token, "refresh-token")
        self.assertEqual(auth_state.connected_email, "user@example.com")
        self.assertRedirects(response, reverse("dropbox_import"))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Dropbox account connected successfully.", messages)

    @patch("media_importer.views.exchange_code_for_tokens", side_effect=DropboxOAuthError("boom"))
    def test_oauth_callback_failure_does_not_activate_connection(self, mock_exchange_code_for_tokens):
        response = self.client.get(reverse("dropbox_oauth_callback"), {"code": "oauth-code"}, follow=True)

        auth_state = DropboxAuthState.get_solo()
        self.assertFalse(auth_state.is_active)
        self.assertEqual(auth_state.refresh_token, "")
        self.assertRedirects(response, reverse("dropbox_import"))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("boom", messages)
        mock_exchange_code_for_tokens.assert_called_once()

    def test_disconnect_view_clears_auth_state(self):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "refresh-token"
        auth_state.connected_email = "user@example.com"
        auth_state.connected_name = "Example User"
        auth_state.is_active = True
        auth_state.save()

        response = self.client.post(reverse("dropbox_oauth_disconnect"), follow=True)

        auth_state.refresh_from_db()
        self.assertFalse(auth_state.is_active)
        self.assertEqual(auth_state.refresh_token, "")
        self.assertRedirects(response, reverse("dropbox_import"))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Dropbox account disconnected.", messages)


@override_settings(
    DROPBOX_APP_KEY="app-key",
    DROPBOX_APP_SECRET="app-secret",
    DROPBOX_REDIRECT_URI="http://127.0.0.1:8000/admin/dropbox-import/oauth/callback/",
    DROPBOX_TO_PUBLISH_FOLDER="/to-publish",
    DROPBOX_PUBLISHED_FOLDER="/published",
)
class DropboxImporterViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.user)

    @patch("media_importer.views.DropboxClient")
    def test_disconnected_state_renders_connect_ui_and_does_not_list_files(self, mock_dropbox_client):
        response = self.client.get(reverse("dropbox_import"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connect Dropbox")
        self.assertContains(response, "Dropbox is not connected yet.")
        mock_dropbox_client.assert_not_called()

    @patch("media_importer.views.DropboxClient")
    def test_connected_state_attempts_to_list_files(self, mock_dropbox_client):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "refresh-token"
        auth_state.connected_email = "user@example.com"
        auth_state.connected_name = "Example User"
        auth_state.is_active = True
        auth_state.save()

        file_info = SimpleNamespace(
            id="id-1",
            name="photo.jpg",
            path_display="/to-publish/photo.jpg",
            server_modified=None,
        )
        client_instance = mock_dropbox_client.return_value
        client_instance.list_image_files.return_value = [file_info]
        client_instance.get_thumbnail_data_url.return_value = "data:image/jpeg;base64,abc123"

        response = self.client.get(reverse("dropbox_import"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disconnect Dropbox")
        self.assertContains(response, "Example User")
        self.assertContains(response, "Innflutningur í gangi")
        client_instance.list_image_files.assert_called_once()

    @patch("media_importer.views.DropboxClient")
    def test_import_post_fails_gracefully_when_disconnected(self, mock_dropbox_client):
        response = self.client.post(reverse("dropbox_import"), {"selected_files": ["/to-publish/photo.jpg"]}, follow=True)

        self.assertRedirects(response, reverse("dropbox_import"))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Dropbox is not connected yet.", messages)
        mock_dropbox_client.assert_not_called()
