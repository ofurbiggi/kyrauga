from types import SimpleNamespace
from unittest.mock import Mock, patch

import dropbox
from django.test import TestCase, override_settings

from media_importer.models import DropboxAuthState
from media_importer.services.dropbox_client import DropboxClient, DropboxClientError


def build_sdk_mock(mock_dropbox):
    return SimpleNamespace(
        Dropbox=mock_dropbox,
        exceptions=dropbox.exceptions,
        files=dropbox.files,
    )


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

    @patch("media_importer.services.dropbox_client.load_dropbox_sdk")
    def test_uses_stored_refresh_token_when_auth_state_exists(self, mock_load_dropbox_sdk):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "stored-refresh-token"
        auth_state.is_active = True
        auth_state.save()

        mock_dropbox = Mock()
        mock_load_dropbox_sdk.return_value = build_sdk_mock(mock_dropbox)
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

    @patch("media_importer.services.dropbox_client.load_dropbox_sdk")
    def test_thumbnail_request_wraps_path_in_path_or_link(self, mock_load_dropbox_sdk):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "stored-refresh-token"
        auth_state.is_active = True
        auth_state.save()

        mock_dropbox = Mock()
        mock_load_dropbox_sdk.return_value = build_sdk_mock(mock_dropbox)
        sdk_client = Mock()
        response = Mock()
        response.content = b"thumbnail-bytes"
        sdk_client.files_get_thumbnail_v2.return_value = (Mock(), response)
        mock_dropbox.return_value = sdk_client

        client = DropboxClient()
        data_url = client.get_thumbnail_data_url("/to-publish/photo.jpg")

        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        resource = sdk_client.files_get_thumbnail_v2.call_args.args[0]
        self.assertTrue(resource.is_path())
        self.assertEqual(resource.get_path(), "/to-publish/photo.jpg")

    @patch(
        "media_importer.services.dropbox_client.load_dropbox_sdk",
        side_effect=DropboxClientError(
            "Dropbox importer is unavailable because the Dropbox Python SDK is not installed."
        ),
    )
    def test_missing_dropbox_sdk_raises_clear_error(self, mock_load_dropbox_sdk):
        with self.assertRaises(DropboxClientError) as exc:
            DropboxClient()

        self.assertEqual(
            str(exc.exception),
            "Dropbox importer is unavailable because the Dropbox Python SDK is not installed.",
        )
