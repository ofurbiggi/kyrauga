from datetime import datetime, timedelta
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.files.base import ContentFile
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from wagtail.admin.views.generic import WagtailAdminTemplateMixin

from wagtail.images import get_image_model

from .services.dropbox_client import DropboxClient, DropboxClientError, load_dropbox_sdk
from .services.importer import apply_import_metadata
from .services.dropbox_oauth import DropboxOAuthError, build_authorize_url, exchange_code_for_tokens
from .models import DropboxAuthState, ImportedDropboxAsset

logger = logging.getLogger(__name__)
IMPORT_DRAFTS_SESSION_KEY = "dropbox_import_drafts"


class AdminAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.is_active and user.is_staff


class DropboxOAuthStartView(AdminAccessMixin, View):
    def get(self, request, *args, **kwargs):
        try:
            return redirect(build_authorize_url())
        except DropboxOAuthError as exc:
            messages.error(request, str(exc))
            return redirect("dropbox_import")


class DropboxOAuthCallbackView(AdminAccessMixin, View):
    def get(self, request, *args, **kwargs):
        code = request.GET.get("code")
        if not code:
            messages.error(request, "No Dropbox authorization code was provided.")
            return redirect("dropbox_import")

        try:
            token_data = exchange_code_for_tokens(code)
            auth_state = DropboxAuthState.get_solo()
            auth_state.refresh_token = token_data["refresh_token"]
            auth_state.connected_account_id = token_data.get("account_id", "")
            auth_state.is_active = True
            auth_state.connected_at = timezone.now()

            expires_in = token_data.get("expires_in")
            auth_state.access_token_expires_at = (
                timezone.now() + timedelta(seconds=int(expires_in))
                if expires_in
                else None
            )

            account_info = self._fetch_account_info(token_data)
            auth_state.connected_email = account_info.get("email", "")
            auth_state.connected_name = account_info.get("name", "")
            if account_info.get("account_id"):
                auth_state.connected_account_id = account_info["account_id"]
            auth_state.save()
        except DropboxOAuthError as exc:
            messages.error(request, str(exc))
            return redirect("dropbox_import")

        messages.success(request, "Dropbox account connected successfully.")
        return redirect("dropbox_import")

    def _fetch_account_info(self, token_data):
        access_token = token_data.get("access_token")
        if not access_token:
            return {}

        try:
            dropbox = load_dropbox_sdk()
            client = dropbox.Dropbox(oauth2_access_token=access_token)
            account = client.users_get_current_account()
        except DropboxClientError as exc:
            logger.warning("Could not fetch Dropbox account info: %s", exc)
            return {}
        except Exception:
            return {}

        return {
            "account_id": getattr(account, "account_id", ""),
            "email": getattr(account, "email", ""),
            "name": getattr(getattr(account, "name", None), "display_name", ""),
        }


class DropboxOAuthDisconnectView(AdminAccessMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = ""
        auth_state.connected_account_id = ""
        auth_state.connected_email = ""
        auth_state.connected_name = ""
        auth_state.access_token_expires_at = None
        auth_state.is_active = False
        auth_state.connected_at = None
        auth_state.save()
        messages.success(request, "Dropbox account disconnected.")
        return redirect("dropbox_import")


class DropboxImportView(AdminAccessMixin, WagtailAdminTemplateMixin, TemplateView):
    template_name = 'media_importer/dropbox_import_index.html'
    page_title = "Import images"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        auth_state = DropboxAuthState.get_solo()
        context["auth_state"] = auth_state
        context["is_connected"] = auth_state.is_active and bool(auth_state.refresh_token)
        context["oauth_start_url"] = reverse("dropbox_oauth_start")
        context["oauth_disconnect_url"] = reverse("dropbox_oauth_disconnect")
        context["imported_assets_url"] = reverse("wagtailsnippets_media_importer_importeddropboxasset:list")
        context["files"] = []
        context["import_stage"] = "select"

        if not context["is_connected"]:
            context["connection_message"] = (
                "Dropbox is not connected yet. Connect your account once to enable imports."
            )
            return context

        try:
            client = DropboxClient()
            files = client.list_image_files()
            imported_ids = set(ImportedDropboxAsset.objects.values_list('dropbox_file_id', flat=True))
            for file in files:
                file.is_imported = file.id in imported_ids
                file.thumbnail_url = client.get_thumbnail_data_url(file.path_display)
            context['files'] = files
        except DropboxClientError as e:
            logger.warning("Failed to load Dropbox files for importer view: %s", e)
            context['error'] = str(e)
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "confirm_import":
            return self._confirm_import(request)

        auth_state = DropboxAuthState.get_solo()
        if not (auth_state.is_active and auth_state.refresh_token):
            messages.error(request, "Dropbox is not connected yet.")
            return redirect("dropbox_import")

        selected_paths = request.POST.getlist('selected_files')
        if not selected_paths:
            messages.error(request, 'No files selected.')
            return redirect("dropbox_import")

        Image = get_image_model()
        success_count = 0
        error_count = 0

        try:
            client = DropboxClient()
            files = client.list_image_files()
            file_dict = {f.path_display: f for f in files}
        except DropboxClientError as exc:
            logger.warning("Could not prepare Dropbox import POST: %s", exc)
            messages.error(request, str(exc))
            return redirect("dropbox_import")

        if request.POST.get("edit_descriptions") == "1":
            return self._render_description_confirmation(request, client, file_dict, selected_paths)

        for path in selected_paths:
            file_info = file_dict.get(path)
            if not file_info:
                messages.error(request, f'File not found: {path}')
                error_count += 1
                continue

            if ImportedDropboxAsset.objects.filter(dropbox_file_id=file_info.id).exists():
                messages.warning(request, f'{file_info.name} already imported.')
                continue

            try:
                logger.info(
                    "Starting Dropbox image import",
                    extra={
                        "dropbox_file_id": file_info.id,
                        "dropbox_path": file_info.path_display,
                        "file_name": file_info.name,
                    },
                )
                file_bytes = client.download_file(file_info.path_display)
                img = Image(
                    file=ContentFile(file_bytes, name=file_info.name),
                    title=file_info.name
                )
                img.save()
                apply_import_metadata(img, file_bytes, file_info)
                ImportedDropboxAsset.objects.create(
                    dropbox_file_id=file_info.id,
                    dropbox_path_lower=file_info.path_lower,
                    dropbox_path_display=file_info.path_display,
                    dropbox_content_hash=file_info.content_hash,
                    dropbox_rev=file_info.rev,
                    server_modified=file_info.server_modified,
                    file_size=file_info.size,
                    wagtail_image=img,
                    status='imported'
                )
                client.move_file(file_info.path_display)
                logger.info(
                    "Completed Dropbox image import",
                    extra={
                        "dropbox_file_id": file_info.id,
                        "dropbox_path": file_info.path_display,
                        "image_id": img.pk,
                        "file_name": file_info.name,
                    },
                )
                success_count += 1
            except Exception as e:
                logger.exception(
                    "Error importing Dropbox image",
                    extra={
                        "dropbox_file_id": getattr(file_info, "id", ""),
                        "dropbox_path": getattr(file_info, "path_display", ""),
                        "file_name": getattr(file_info, "name", ""),
                    },
                )
                messages.error(request, f'Error importing {file_info.name}: {str(e)}')
                error_count += 1

        if success_count:
            messages.success(request, f'Successfully imported {success_count} files.')
        if error_count:
            messages.error(request, f'Failed to import {error_count} files.')
        return redirect("dropbox_import")

    def _render_description_confirmation(self, request, client, file_dict, selected_paths):
        drafts = []

        for path in selected_paths:
            file_info = file_dict.get(path)
            if not file_info:
                messages.error(request, f'File not found: {path}')
                continue

            if ImportedDropboxAsset.objects.filter(dropbox_file_id=file_info.id).exists():
                messages.warning(request, f'{file_info.name} already imported.')
                continue

            try:
                file_bytes = client.download_file(file_info.path_display)
                metadata = self._extract_metadata(file_bytes)
                drafts.append(
                    {
                        "file_id": file_info.id,
                        "name": file_info.name,
                        "path_display": file_info.path_display,
                        "path_lower": file_info.path_lower,
                        "content_hash": file_info.content_hash,
                        "rev": file_info.rev,
                        "server_modified": file_info.server_modified.isoformat() if file_info.server_modified else "",
                        "size": file_info.size,
                        "thumbnail_url": client.get_thumbnail_data_url(file_info.path_display) or "",
                        "metadata": self._serialize_metadata(metadata),
                        "description": self._build_description(metadata, file_info),
                    }
                )
            except Exception as exc:
                logger.exception("Error preparing Dropbox description edit draft")
                messages.error(request, f"Error preparing {file_info.name}: {exc}")

        if not drafts:
            messages.error(request, "No files were ready for import.")
            return redirect("dropbox_import")

        request.session[IMPORT_DRAFTS_SESSION_KEY] = drafts
        context = self.get_context_data()
        context["import_stage"] = "confirm_descriptions"
        context["drafts"] = [self._build_draft_preview(draft) for draft in drafts]
        return self.render_to_response(context)

    def _confirm_import(self, request):
        auth_state = DropboxAuthState.get_solo()
        if not (auth_state.is_active and auth_state.refresh_token):
            messages.error(request, "Dropbox is not connected yet.")
            return redirect("dropbox_import")

        drafts = request.session.get(IMPORT_DRAFTS_SESSION_KEY, [])
        if not drafts:
            messages.error(request, "Description edit session expired. Please select your files again.")
            return redirect("dropbox_import")

        Image = get_image_model()
        success_count = 0
        error_count = 0

        try:
            client = DropboxClient()
            files = client.list_image_files()
            file_dict = {f.path_display: f for f in files}
        except DropboxClientError as exc:
            logger.warning("Could not prepare Dropbox confirmation POST: %s", exc)
            messages.error(request, str(exc))
            return redirect("dropbox_import")

        for index, draft in enumerate(drafts):
            file_info = file_dict.get(draft["path_display"])
            if not file_info:
                messages.error(request, f"File not found: {draft['path_display']}")
                error_count += 1
                continue

            if ImportedDropboxAsset.objects.filter(dropbox_file_id=file_info.id).exists():
                messages.warning(request, f"{file_info.name} already imported.")
                continue

            try:
                logger.info(
                    "Starting Dropbox image import with description editing",
                    extra={
                        "dropbox_file_id": file_info.id,
                        "dropbox_path": file_info.path_display,
                        "file_name": file_info.name,
                    },
                )
                file_bytes = client.download_file(file_info.path_display)
                img = Image(
                    file=ContentFile(file_bytes, name=file_info.name),
                    title=file_info.name,
                )
                img.save()
                apply_import_metadata(
                    img,
                    file_bytes,
                    file_info,
                    description_override=request.POST.get(f"description__{index}", draft["description"]).strip(),
                    metadata=self._deserialize_metadata(draft["metadata"]),
                )
                ImportedDropboxAsset.objects.create(
                    dropbox_file_id=file_info.id,
                    dropbox_path_lower=file_info.path_lower,
                    dropbox_path_display=file_info.path_display,
                    dropbox_content_hash=file_info.content_hash,
                    dropbox_rev=file_info.rev,
                    server_modified=file_info.server_modified,
                    file_size=file_info.size,
                    wagtail_image=img,
                    status="imported",
                )
                client.move_file(file_info.path_display)
                success_count += 1
            except Exception as exc:
                logger.exception(
                    "Error importing Dropbox image after description editing",
                    extra={
                        "dropbox_file_id": getattr(file_info, "id", ""),
                        "dropbox_path": getattr(file_info, "path_display", ""),
                        "file_name": getattr(file_info, "name", ""),
                    },
                )
                messages.error(request, f"Error importing {file_info.name}: {exc}")
                error_count += 1

        request.session.pop(IMPORT_DRAFTS_SESSION_KEY, None)
        if success_count:
            messages.success(request, f"Successfully imported {success_count} files.")
        if error_count:
            messages.error(request, f"Failed to import {error_count} files.")
        return redirect("dropbox_import")

    def _extract_metadata(self, file_bytes):
        from .services.importer import extract_photo_metadata

        return extract_photo_metadata(file_bytes)

    def _build_description(self, metadata, file_info):
        from .services.importer import build_icelandic_description

        return build_icelandic_description(metadata, file_info=file_info)

    def _serialize_metadata(self, metadata):
        serialized = {
            "camera_make": metadata.get("camera_make", ""),
            "camera_model": metadata.get("camera_model", ""),
            "lens_model": metadata.get("lens_model", ""),
            "shutter_speed": metadata.get("shutter_speed", ""),
            "location_name": metadata.get("location_name", ""),
            "location_city": metadata.get("location_city", ""),
            "location_country": metadata.get("location_country", ""),
        }
        if metadata.get("taken_at"):
            serialized["taken_at"] = metadata["taken_at"].isoformat()
        if metadata.get("focal_length_mm") is not None:
            serialized["focal_length_mm"] = str(metadata["focal_length_mm"])
        if metadata.get("aperture") is not None:
            serialized["aperture"] = str(metadata["aperture"])
        if metadata.get("iso") is not None:
            serialized["iso"] = int(metadata["iso"])
        gps = metadata.get("gps") or {}
        if gps:
            serialized["gps"] = {
                "latitude": float(gps["latitude"]),
                "longitude": float(gps["longitude"]),
            }
        return serialized

    def _deserialize_metadata(self, metadata):
        result = dict(metadata)
        if result.get("taken_at"):
            result["taken_at"] = datetime.fromisoformat(result["taken_at"])
        if result.get("focal_length_mm") not in (None, ""):
            result["focal_length_mm"] = Decimal(result["focal_length_mm"])
        if result.get("aperture") not in (None, ""):
            result["aperture"] = Decimal(result["aperture"])
        return result

    def _build_draft_preview(self, draft):
        metadata = self._deserialize_metadata(draft["metadata"])
        metadata_items = [
            ("Taken at", metadata["taken_at"].strftime("%Y-%m-%d %H:%M")) if metadata.get("taken_at") else None,
            ("Camera make", metadata.get("camera_make", "")),
            ("Camera model", metadata.get("camera_model", "")),
            ("Lens model", metadata.get("lens_model", "")),
            ("Focal length", f"{metadata['focal_length_mm']} mm") if metadata.get("focal_length_mm") is not None else None,
            ("Shutter speed", metadata.get("shutter_speed", "")),
            ("Aperture", f"f/{metadata['aperture']}") if metadata.get("aperture") is not None else None,
            ("ISO", str(metadata["iso"])) if metadata.get("iso") is not None else None,
        ]
        gps = metadata.get("gps") or {}
        if gps.get("latitude") is not None and gps.get("longitude") is not None:
            metadata_items.append(
                ("GPS", f"{gps['latitude']:.5f}, {gps['longitude']:.5f}")
            )
        return {
            **draft,
            "metadata_items": [item for item in metadata_items if item and item[1]],
        }
