from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from media_importer.services.dropbox_oauth import (
    DropboxOAuthError,
    build_authorize_url,
    exchange_code_for_tokens,
)


@override_settings(
    DROPBOX_APP_KEY="app-key",
    DROPBOX_APP_SECRET="app-secret",
    DROPBOX_REDIRECT_URI="http://127.0.0.1:8000/admin/dropbox-import/oauth/callback/",
)
class DropboxOAuthHelperTests(SimpleTestCase):
    def test_authorize_url_contains_expected_parameters(self):
        url = build_authorize_url()
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "www.dropbox.com")
        self.assertEqual(params["client_id"], ["app-key"])
        self.assertEqual(params["redirect_uri"], ["http://127.0.0.1:8000/admin/dropbox-import/oauth/callback/"])
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["token_access_type"], ["offline"])

    @patch("media_importer.services.dropbox_oauth.requests.post")
    def test_exchange_code_handles_success_response(self, mock_post):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "account_id": "dbid:123",
            "expires_in": 14400,
        }
        mock_post.return_value = response

        payload = exchange_code_for_tokens("auth-code")

        self.assertEqual(payload["refresh_token"], "refresh-token")
        mock_post.assert_called_once()

    @patch("media_importer.services.dropbox_oauth.requests.post")
    def test_exchange_code_raises_clean_exception_on_http_failure(self, mock_post):
        response = Mock()
        response.ok = False
        response.json.return_value = {"error_description": "bad code"}
        mock_post.return_value = response

        with self.assertRaises(DropboxOAuthError) as exc:
            exchange_code_for_tokens("bad-code")

        self.assertIn("bad code", str(exc.exception))
