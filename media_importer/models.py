from django.db import models
from wagtail.images import get_image_model_string


class DropboxAuthState(models.Model):
    refresh_token = models.TextField(blank=True)
    connected_account_id = models.CharField(max_length=255, blank=True)
    connected_email = models.EmailField(blank=True)
    connected_name = models.CharField(max_length=255, blank=True)
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    connected_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance

    def __str__(self):
        if self.is_active:
            identity = self.connected_email or self.connected_name or self.connected_account_id or "connected"
            return f"Dropbox connection ({identity})"
        return "Dropbox connection (disconnected)"


class ImportedDropboxAsset(models.Model):
    STATUS_CHOICES = [
        ('imported', 'Imported'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    ]

    dropbox_file_id = models.CharField(max_length=255, unique=True, help_text="Dropbox file ID")
    dropbox_path_lower = models.CharField(max_length=500, help_text="Lowercase Dropbox path")
    dropbox_path_display = models.CharField(max_length=500, help_text="Display Dropbox path")
    dropbox_content_hash = models.CharField(max_length=255, help_text="Dropbox content hash")
    dropbox_rev = models.CharField(max_length=255, help_text="Dropbox revision")
    server_modified = models.DateTimeField(null=True, blank=True, help_text="When the file was last modified on Dropbox")
    file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    wagtail_image = models.ForeignKey(
        get_image_model_string(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dropbox_import_records",
        help_text="The corresponding Wagtail image"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='imported',
        help_text="Import status"
    )
    notes = models.TextField(blank=True, help_text="Optional notes about the import")
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-imported_at']
        constraints = [
            models.UniqueConstraint(fields=['dropbox_file_id'], name='unique_dropbox_file_id')
        ]

    def __str__(self):
        return self.dropbox_path_display
