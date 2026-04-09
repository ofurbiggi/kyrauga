from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import datetime


from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import FileMetadata

from media_importer.models import DropboxAuthState


@dataclass
class DropboxFileInfo:
    id: str
    name: str
    path_lower: str
    path_display: str
    content_hash: str
    rev: str
    server_modified: Optional[datetime]
    size: int


class DropboxClientError(Exception):
    pass


class DropboxClient:
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

    def __init__(self):
        self.app_key = getattr(settings, "DROPBOX_APP_KEY", None)
        self.app_secret = getattr(settings, "DROPBOX_APP_SECRET", None)
        self.to_publish_folder = getattr(settings, "DROPBOX_TO_PUBLISH_FOLDER", None)
        self.published_folder = getattr(settings, "DROPBOX_PUBLISHED_FOLDER", None)
        self.auth_state = DropboxAuthState.get_solo()
        self.refresh_token = self.auth_state.refresh_token if self.auth_state.is_active else ""

        self._validate_settings()
        self.client = self._create_client()

    def _validate_settings(self) -> None:
        missing = [
            name
            for name in [
                "DROPBOX_APP_KEY",
                "DROPBOX_APP_SECRET",
                "DROPBOX_TO_PUBLISH_FOLDER",
                "DROPBOX_PUBLISHED_FOLDER",
            ]
            if not getattr(settings, name, None)
        ]
        if missing:
            raise ImproperlyConfigured(
                f"Missing Dropbox settings: {', '.join(missing)}"
            )
        if not self.refresh_token:
            raise DropboxClientError("Dropbox is not connected")

    def _create_client(self) -> dropbox.Dropbox:
        try:
            client = dropbox.Dropbox(
                oauth2_refresh_token=self.refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )
            client.users_get_current_account()
            return client
        except AuthError as exc:
            raise DropboxClientError("Dropbox authentication failed") from exc
        except Exception as exc:
            raise DropboxClientError("Unable to create Dropbox client") from exc

    def list_image_files(self, folder: Optional[str] = None) -> List[DropboxFileInfo]:
        folder_path = folder or self.to_publish_folder
        try:
            result = self.client.files_list_folder(folder_path, recursive=False)
        except ApiError as exc:
            raise DropboxClientError(f"Could not list folder {folder_path}") from exc

        files: List[DropboxFileInfo] = []
        while True:
            for entry in result.entries:
                if self._is_image_file(entry):
                    files.append(self._convert_entry(entry))
            if not result.has_more:
                break
            result = self.client.files_list_folder_continue(result.cursor)

        files.sort(key=lambda x: x.server_modified, reverse=True)
        return files

    def download_file(self, path: str, dest_path: Optional[str] = None) -> bytes:
        try:
            _, response = self.client.files_download(path)
            file_bytes = response.content
        except ApiError as exc:
            raise DropboxClientError(f"Failed to download {path}") from exc

        if dest_path:
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(file_bytes)
        return file_bytes

    def move_file(self, source_path: str, destination_path: Optional[str] = None) -> str:
        destination = self._build_destination_path(source_path, destination_path)
        try:
            result = self.client.files_move_v2(source_path, destination, autorename=True)
            return result.metadata.path_display
        except ApiError as exc:
            raise DropboxClientError(f"Failed to move {source_path} to {destination}") from exc

    def get_temporary_link(self, path: str) -> Optional[str]:
        try:
            link_metadata = self.client.files_get_temporary_link(path)
            return link_metadata.link
        except ApiError:
            return None

    def _is_image_file(self, entry) -> bool:
        if not isinstance(entry, FileMetadata):
            return False
        return Path(entry.name).suffix.lower() in self.IMAGE_EXTENSIONS

    def _convert_entry(self, entry: FileMetadata) -> DropboxFileInfo:
        return DropboxFileInfo(
            id=entry.id,
            name=entry.name,
            path_lower=entry.path_lower,
            path_display=entry.path_display,
            content_hash=entry.content_hash,
            rev=entry.rev,
            server_modified=entry.server_modified,
            size=entry.size,
        )

    def _build_destination_path(self, source_path: str, destination_path: Optional[str]) -> str:
        if destination_path:
            return destination_path
        filename = Path(source_path).name
        folder = self.published_folder.rstrip("/")
        return f"{folder}/{filename}"
