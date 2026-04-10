from urllib.parse import urlencode

import requests
from django.conf import settings


class DropboxOAuthError(Exception):
    pass


def _get_required_setting(name):
    value = getattr(settings, name, None)
    if not value:
        raise DropboxOAuthError(f"Missing Dropbox setting: {name}")
    return value


def build_authorize_url():
    params = urlencode(
        {
            "client_id": _get_required_setting("DROPBOX_APP_KEY"),
            "redirect_uri": _get_required_setting("DROPBOX_REDIRECT_URI"),
            "response_type": "code",
            "token_access_type": "offline",
        }
    )
    return f"https://www.dropbox.com/oauth2/authorize?{params}"


def exchange_code_for_tokens(code):
    if not code:
        raise DropboxOAuthError("Missing Dropbox authorization code")

    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": _get_required_setting("DROPBOX_APP_KEY"),
        "client_secret": _get_required_setting("DROPBOX_APP_SECRET"),
        "redirect_uri": _get_required_setting("DROPBOX_REDIRECT_URI"),
    }

    try:
        response = requests.post(
            "https://api.dropboxapi.com/oauth2/token",
            data=data,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise DropboxOAuthError("Could not reach Dropbox OAuth service") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise DropboxOAuthError("Dropbox OAuth returned an invalid response") from exc

    if not response.ok:
        error_description = payload.get("error_description") or payload.get("error")
        raise DropboxOAuthError(
            f"Dropbox OAuth token exchange failed: {error_description or 'unknown error'}"
        )

    if not payload.get("refresh_token"):
        raise DropboxOAuthError("Dropbox OAuth response did not include a refresh token")

    return payload
