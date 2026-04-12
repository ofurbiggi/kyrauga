from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image as PILImage
from io import BytesIO

from media_importer.models import DropboxAuthState
from media_importer.services.dropbox_client import DropboxClientError
from media_importer.services.dropbox_oauth import DropboxOAuthError


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(
    DROPBOX_APP_KEY="app-key",
    DROPBOX_APP_SECRET="app-secret",
    DROPBOX_REDIRECT_URI="http://127.0.0.1:8000/admin/dropbox-import/oauth/callback/",
    DROPBOX_TO_PUBLISH_FOLDER="/to-publish",
    DROPBOX_PUBLISHED_FOLDER="/published",
    STORAGES=TEST_STORAGES,
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

        response = self.client.get(reverse("dropbox_oauth_callback"), {"code": "oauth-code"})

        auth_state = DropboxAuthState.get_solo()
        self.assertTrue(auth_state.is_active)
        self.assertEqual(auth_state.refresh_token, "refresh-token")
        self.assertEqual(auth_state.connected_email, "user@example.com")
        self.assertRedirects(response, reverse("dropbox_import"), fetch_redirect_response=False)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Dropbox account connected successfully.", messages)

    @patch("media_importer.views.exchange_code_for_tokens", side_effect=DropboxOAuthError("boom"))
    def test_oauth_callback_failure_does_not_activate_connection(self, mock_exchange_code_for_tokens):
        response = self.client.get(reverse("dropbox_oauth_callback"), {"code": "oauth-code"})

        auth_state = DropboxAuthState.get_solo()
        self.assertFalse(auth_state.is_active)
        self.assertEqual(auth_state.refresh_token, "")
        self.assertRedirects(response, reverse("dropbox_import"), fetch_redirect_response=False)
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
        self.assertRedirects(response, reverse("dropbox_import"), fetch_redirect_response=False)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Dropbox account disconnected.", messages)


@override_settings(
    DROPBOX_APP_KEY="app-key",
    DROPBOX_APP_SECRET="app-secret",
    DROPBOX_REDIRECT_URI="http://127.0.0.1:8000/admin/dropbox-import/oauth/callback/",
    DROPBOX_TO_PUBLISH_FOLDER="/to-publish",
    DROPBOX_PUBLISHED_FOLDER="/published",
    STORAGES=TEST_STORAGES,
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
        self.assertContains(response, "View imported Dropbox assets")
        client_instance.list_image_files.assert_called_once()

    @patch(
        "media_importer.views.DropboxClient",
        side_effect=DropboxClientError("Dropbox importer is unavailable."),
    )
    def test_connected_state_shows_error_when_dropbox_client_is_unavailable(self, mock_dropbox_client):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "refresh-token"
        auth_state.is_active = True
        auth_state.save()

        response = self.client.get(reverse("dropbox_import"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dropbox importer is unavailable.")
        mock_dropbox_client.assert_called_once()

    @patch("media_importer.views.DropboxClient")
    def test_import_post_fails_gracefully_when_disconnected(self, mock_dropbox_client):
        response = self.client.post(reverse("dropbox_import"), {"selected_files": ["/to-publish/photo.jpg"]}, follow=True)

        self.assertRedirects(response, reverse("dropbox_import"), fetch_redirect_response=False)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Dropbox is not connected yet.", messages)
        mock_dropbox_client.assert_not_called()

    @patch(
        "media_importer.views.DropboxClient",
        side_effect=DropboxClientError("Missing Dropbox settings: DROPBOX_APP_KEY"),
    )
    def test_import_post_fails_gracefully_when_client_cannot_start(self, mock_dropbox_client):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "refresh-token"
        auth_state.is_active = True
        auth_state.save()

        response = self.client.post(
            reverse("dropbox_import"),
            {"selected_files": ["/to-publish/photo.jpg"]},
        )

        self.assertRedirects(response, reverse("dropbox_import"), fetch_redirect_response=False)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Missing Dropbox settings: DROPBOX_APP_KEY", messages)
        mock_dropbox_client.assert_called_once()

    @patch("media_importer.views.DropboxImportView._extract_metadata")
    @patch("media_importer.views.DropboxClient")
    def test_edit_descriptions_option_renders_confirmation_view(
        self,
        mock_dropbox_client,
        mock_extract_metadata,
    ):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "refresh-token"
        auth_state.connected_name = "Example User"
        auth_state.is_active = True
        auth_state.save()

        file_info = SimpleNamespace(
            id="id-1",
            name="photo.jpg",
            path_lower="/to-publish/photo.jpg",
            path_display="/to-publish/photo.jpg",
            content_hash="hash-1",
            rev="rev-1",
            server_modified=timezone.now(),
            size=1234,
        )
        client_instance = mock_dropbox_client.return_value
        client_instance.list_image_files.return_value = [file_info]
        client_instance.download_file.return_value = self._build_test_image_bytes()
        client_instance.get_thumbnail_data_url.return_value = "data:image/jpeg;base64,abc123"
        mock_extract_metadata.return_value = {"camera_model": "X-T4"}

        response = self.client.post(
            reverse("dropbox_import"),
            {"selected_files": [file_info.path_display], "edit_descriptions": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit descriptions")
        self.assertContains(response, "photo.jpg")
        self.assertIn("dropbox_import_drafts", self.client.session)

    @patch("media_importer.views.DropboxClient")
    def test_confirm_import_uses_edited_description_when_option_selected(self, mock_dropbox_client):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "refresh-token"
        auth_state.is_active = True
        auth_state.save()

        session = self.client.session
        session["dropbox_import_drafts"] = [
            {
                "file_id": "id-1",
                "name": "photo.jpg",
                "path_display": "/to-publish/photo.jpg",
                "path_lower": "/to-publish/photo.jpg",
                "content_hash": "hash-1",
                "rev": "rev-1",
                "server_modified": "",
                "size": 1234,
                "thumbnail_url": "data:image/jpeg;base64,abc123",
                "metadata": {
                    "camera_make": "FUJIFILM",
                    "camera_model": "X-T4",
                    "lens_model": "",
                    "shutter_speed": "",
                    "location_name": "",
                    "location_city": "",
                    "location_country": "",
                },
                "description": "Sjálfgefin lýsing.",
            }
        ]
        session.save()

        file_info = SimpleNamespace(
            id="id-1",
            name="photo.jpg",
            path_lower="/to-publish/photo.jpg",
            path_display="/to-publish/photo.jpg",
            content_hash="hash-1",
            rev="rev-1",
            server_modified=None,
            size=1234,
        )
        client_instance = mock_dropbox_client.return_value
        client_instance.list_image_files.return_value = [file_info]
        client_instance.download_file.return_value = self._build_test_image_bytes()
        client_instance.move_file.return_value = "/published/photo.jpg"

        response = self.client.post(
            reverse("dropbox_import"),
            {"action": "confirm_import", "description__0": "Handskrifuð lýsing."},
            follow=True,
        )

        self.assertRedirects(response, reverse("dropbox_import"))
        from wagtail.images import get_image_model

        image = get_image_model().objects.get(title="photo.jpg")
        self.assertEqual(image.description, "Handskrifuð lýsing.")

    def _build_test_image_bytes(self):
        buffer = BytesIO()
        image = PILImage.new("RGB", (20, 20), color="red")
        image.save(buffer, format="JPEG")
        return buffer.getvalue()

    def test_wagtail_images_index_contains_import_link(self):
        response = self.client.get(reverse("wagtailimages:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("dropbox_import"))
        self.assertContains(response, "Import images")
