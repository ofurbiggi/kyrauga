from django.conf import settings
from django.db import models
from django.utils import timezone
from urllib.parse import urlencode
from wagtail.images import get_image_model_string
from wagtail.images.models import AbstractImage, AbstractRendition, Image as WagtailImage


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


class CustomImage(AbstractImage):
    taken_at = models.DateTimeField(null=True, blank=True)
    camera_make = models.CharField(max_length=255, blank=True)
    camera_model = models.CharField(max_length=255, blank=True)
    lens_model = models.CharField(max_length=255, blank=True)
    focal_length_mm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    shutter_speed = models.CharField(max_length=64, blank=True)
    aperture = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    iso = models.PositiveIntegerField(null=True, blank=True)
    gps_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_name = models.CharField(max_length=255, blank=True)
    location_city = models.CharField(max_length=255, blank=True)
    location_country = models.CharField(max_length=255, blank=True)

    metadata_field_names = (
        "taken_at",
        "camera_make",
        "camera_model",
        "lens_model",
        "focal_length_mm",
        "shutter_speed",
        "aperture",
        "iso",
        "gps_latitude",
        "gps_longitude",
        "location_name",
        "location_city",
        "location_country",
    )

    admin_form_fields = list(WagtailImage.admin_form_fields) + list(metadata_field_names)

    def metadata_items(self):
        items = []

        if self.taken_at:
            local_taken_at = timezone.localtime(self.taken_at) if timezone.is_aware(self.taken_at) else self.taken_at
            items.append(("Taken at", local_taken_at.strftime("%Y-%m-%d %H:%M")))

        for label, value in (
            ("Camera make", self.camera_make),
            ("Camera model", self.camera_model),
            ("Lens model", self.lens_model),
            ("Focal length", f"{self.focal_length_mm} mm" if self.focal_length_mm is not None else ""),
            ("Shutter speed", self.shutter_speed),
            ("Aperture", f"f/{self.aperture}" if self.aperture is not None else ""),
            ("ISO", str(self.iso) if self.iso is not None else ""),
            ("Location name", self.location_name),
            ("City", self.location_city),
            ("Country", self.location_country),
            ("GPS latitude", str(self.gps_latitude) if self.gps_latitude is not None else ""),
            ("GPS longitude", str(self.gps_longitude) if self.gps_longitude is not None else ""),
        ):
            if value:
                items.append((label, value))

        return items

    def has_gps_coordinates(self):
        return self.gps_latitude is not None and self.gps_longitude is not None

    def map_embed_url(self):
        if not self.has_gps_coordinates():
            return ""

        latitude = float(self.gps_latitude)
        longitude = float(self.gps_longitude)
        lat_delta = 0.01
        lon_delta = 0.02
        params = urlencode(
            {
                "bbox": f"{longitude - lon_delta},{latitude - lat_delta},{longitude + lon_delta},{latitude + lat_delta}",
                "layer": "mapnik",
                "marker": f"{latitude},{longitude}",
            }
        )
        return f"https://www.openstreetmap.org/export/embed.html?{params}"

    def map_link_url(self):
        if not self.has_gps_coordinates():
            return ""

        latitude = float(self.gps_latitude)
        longitude = float(self.gps_longitude)
        params = urlencode(
            {
                "mlat": latitude,
                "mlon": longitude,
                "zoom": 14,
            }
        )
        return f"https://www.openstreetmap.org/?{params}"


class CustomRendition(AbstractRendition):
    image = models.ForeignKey(
        CustomImage,
        on_delete=models.CASCADE,
        related_name="renditions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("image", "filter_spec", "focal_point_key"),
                name="unique_rendition",
            )
        ]


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


class ImageMetadataHistory(models.Model):
    SOURCE_EXIF = "exif"
    SOURCE_DROPBOX = "dropbox"
    SOURCE_NORMAL = "normal"
    SOURCE_MANUAL = "manual"

    SOURCE_CHOICES = [
        (SOURCE_EXIF, "EXIF"),
        (SOURCE_DROPBOX, "Dropbox"),
        (SOURCE_NORMAL, "Normal"),
        (SOURCE_MANUAL, "Manual"),
    ]

    image = models.ForeignKey(
        get_image_model_string(),
        on_delete=models.CASCADE,
        related_name="metadata_history",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="image_metadata_history_entries",
    )
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]

    def __str__(self):
        return f"Metadata history for {self.image_id} from {self.source}"
