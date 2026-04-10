from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils.html import format_html

from .models import ImportedDropboxAsset
from .views import (
    DropboxImportView,
    DropboxOAuthCallbackView,
    DropboxOAuthDisconnectView,
    DropboxOAuthStartView,
)


class ImportedDropboxAssetViewSet(SnippetViewSet):
    model = ImportedDropboxAsset
    icon = "image"
    menu_label = "Imported Dropbox Assets"
    menu_name = "imported_dropbox_assets"
    list_display = [
        "dropbox_path_display",
        "status",
        "file_size",
        "server_modified",
        "imported_at",
    ]
    search_fields = [
        "dropbox_path_display",
        "dropbox_file_id",
        "dropbox_content_hash",
        "notes",
    ]


register_snippet(ImportedDropboxAssetViewSet)


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [
        path("dropbox-import/", DropboxImportView.as_view(), name="dropbox_import"),
        path("dropbox-import/oauth/start/", DropboxOAuthStartView.as_view(), name="dropbox_oauth_start"),
        path("dropbox-import/oauth/callback/", DropboxOAuthCallbackView.as_view(), name="dropbox_oauth_callback"),
        path("dropbox-import/oauth/disconnect/", DropboxOAuthDisconnectView.as_view(), name="dropbox_oauth_disconnect"),
    ]


@hooks.register('register_admin_menu_item')
def register_dropbox_import_menu_item():
    return MenuItem("Import images", reverse("dropbox_import"), icon_name="download")


@hooks.register("insert_global_admin_css")
def insert_global_admin_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("css/wagtail-admin-branding.css"),
    )
