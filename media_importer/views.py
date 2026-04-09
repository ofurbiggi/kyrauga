from datetime import timedelta
import logging

import dropbox
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

from .services.dropbox_client import DropboxClient, DropboxClientError
from .services.importer import apply_import_metadata
from .services.dropbox_oauth import DropboxOAuthError, build_authorize_url, exchange_code_for_tokens
from .models import DropboxAuthState, ImportedDropboxAsset

logger = logging.getLogger(__name__)


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
            client = dropbox.Dropbox(oauth2_access_token=access_token)
            account = client.users_get_current_account()
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
        context["files"] = []

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
        auth_state = DropboxAuthState.get_solo()
        if not (auth_state.is_active and auth_state.refresh_token):
            messages.error(request, "Dropbox is not connected yet.")
            return redirect("dropbox_import")

        selected_paths = request.POST.getlist('selected_files')
        if not selected_paths:
            messages.error(request, 'No files selected.')
            return redirect("dropbox_import")

        client = DropboxClient()
        Image = get_image_model()
        success_count = 0
        error_count = 0

        # Get current files to map paths to file info
        try:
            files = client.list_image_files()
            file_dict = {f.path_display: f for f in files}
        except DropboxClientError:
            logger.exception("Could not retrieve Dropbox file list during import POST")
            messages.error(request, 'Could not retrieve file list.')
            return redirect("dropbox_import")

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
