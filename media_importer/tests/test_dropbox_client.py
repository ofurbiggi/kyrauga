from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from media_importer.models import DropboxAuthState
from media_importer.services.dropbox_client import DropboxClient, DropboxClientError


@override_settings(
    DROPBOX_APP_KEY="app-key",
    DROPBOX_APP_SECRET="app-secret",
    DROPBOX_TO_PUBLISH_FOLDER="/to-publish",
    DROPBOX_PUBLISHED_FOLDER="/published",
)
class DropboxClientTests(TestCase):
    def test_raises_clear_error_when_not_connected(self):
        DropboxAuthState.get_solo()

        with self.assertRaises(DropboxClientError) as exc:
            DropboxClient()

        self.assertEqual(str(exc.exception), "Dropbox is not connected")

    @patch("media_importer.services.dropbox_client.dropbox.Dropbox")
    def test_uses_stored_refresh_token_when_auth_state_exists(self, mock_dropbox):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "stored-refresh-token"
        auth_state.is_active = True
        auth_state.save()

        sdk_client = Mock()
        mock_dropbox.return_value = sdk_client

        client = DropboxClient()

        self.assertIs(client.client, sdk_client)
        mock_dropbox.assert_called_once_with(
            oauth2_refresh_token="stored-refresh-token",
            app_key="app-key",
            app_secret="app-secret",
        )
        sdk_client.users_get_current_account.assert_called_once()
