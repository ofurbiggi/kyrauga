from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image as PILImage

from wagtail.images import get_image_model

from media_importer.models import DropboxAuthState
from media_importer.services.importer import (
    build_icelandic_description,
    extract_photo_metadata,
    extract_xmp_metadata,
)


class ImporterMetadataTests(TestCase):
    def test_builds_icelandic_description_with_taken_date_and_gps(self):
        description = build_icelandic_description(
            {
                "taken_at": datetime(2024, 8, 17, 21, 35),
                "gps": {
                    "latitude": 64.14658,
                    "longitude": -21.94264,
                },
            }
        )

        self.assertIn("Ljósmynd tekin 17. ágúst 2024 kl. 21:35.", description)
        self.assertIn("Staðsetning samkvæmt GPS-gögnum: 64.14658°N, 21.94264°V.", description)

    def test_falls_back_to_dropbox_timestamp_when_taken_date_missing(self):
        file_info = SimpleNamespace(server_modified=datetime(2024, 9, 2, 10, 15))

        description = build_icelandic_description({}, file_info=file_info)

        self.assertEqual(
            description,
            "Skráin var síðast dagsett í Dropbox 2. september 2024 kl. 10:15.",
        )

    @patch("media_importer.services.importer.PILImage.open")
    def test_extract_photo_metadata_uses_gps_ifd_when_gps_info_value_is_not_mapping(self, mock_open):
        fake_exif = FakeExif(
            values={
                34853: 26,
                271: "FUJIFILM",
            },
            ifd_values={
                34853: {
                    1: "N",
                    2: ((64, 1), (8, 1), (4769, 100)),
                    3: "W",
                    4: ((21, 1), (56, 1), (331, 100)),
                }
            },
        )
        mock_image = mock_open.return_value.__enter__.return_value
        mock_image.getexif.return_value = fake_exif

        metadata = extract_photo_metadata(b"fake-image-bytes")

        self.assertEqual(metadata["camera_make"], "FUJIFILM")
        self.assertAlmostEqual(metadata["gps"]["latitude"], 64.14658, places=4)
        self.assertAlmostEqual(metadata["gps"]["longitude"], -21.93425, places=4)

    @patch("media_importer.services.importer.PILImage.open")
    def test_extract_photo_metadata_skips_unusable_gps_payload_without_crashing(self, mock_open):
        fake_exif = FakeExif(values={34853: 26})
        mock_image = mock_open.return_value.__enter__.return_value
        mock_image.getexif.return_value = fake_exif

        metadata = extract_photo_metadata(b"fake-image-bytes")

        self.assertEqual(metadata, {})

    def test_extract_xmp_metadata_reads_lightroom_lens_and_capture_date(self):
        file_bytes = b"""
        <x:xmpmeta>
            <rdf:Description
                photoshop:DateCreated="2026-03-07T12:16:22"
                aux:Lens="iPhone 15 Pro Max front TrueDepth camera 2.69mm f/1.9"
                exifEX:LensModel="iPhone 15 Pro Max front TrueDepth camera 2.69mm f/1.9"
                aux:LensInfo="469865/174671 469865/174671 19/10 19/10" />
        </x:xmpmeta>
        """

        metadata = extract_xmp_metadata(file_bytes)

        self.assertEqual(
            metadata["lens_model"],
            "iPhone 15 Pro Max front TrueDepth camera 2.69mm f/1.9",
        )
        self.assertEqual(str(metadata["focal_length_mm"]), "2.69")
        self.assertEqual(str(metadata["aperture"]), "1.90")
        self.assertEqual(metadata["taken_at"].year, 2026)
        self.assertEqual(metadata["taken_at"].month, 3)
        self.assertEqual(metadata["taken_at"].day, 7)

    def test_extract_xmp_metadata_can_derive_focal_length_and_aperture_from_lens_model(self):
        file_bytes = b"""
        <x:xmpmeta>
            <rdf:Description
                aux:Lens="iPhone 15 Pro Max back triple camera 15.66mm f/2.8" />
        </x:xmpmeta>
        """

        metadata = extract_xmp_metadata(file_bytes)

        self.assertEqual(
            metadata["lens_model"],
            "iPhone 15 Pro Max back triple camera 15.66mm f/2.8",
        )
        self.assertEqual(str(metadata["focal_length_mm"]), "15.66")
        self.assertEqual(str(metadata["aperture"]), "2.80")

    def test_extract_xmp_metadata_skips_invalid_lens_info_rationals(self):
        file_bytes = b"""
        <x:xmpmeta>
            <rdf:Description
                aux:Lens="XF23mmF2 R WR"
                aux:LensInfo="0/0 0/0 2/1 2/1" />
        </x:xmpmeta>
        """

        metadata = extract_xmp_metadata(file_bytes)

        self.assertEqual(metadata["lens_model"], "XF23mmF2 R WR")
        self.assertEqual(str(metadata["focal_length_mm"]), "23.00")
        self.assertNotIn("aperture", metadata)

    @patch("media_importer.services.importer.PILImage.open")
    def test_xmp_capture_date_wins_when_only_generic_exif_datetime_exists(self, mock_open):
        fake_exif = FakeExif(values={306: "2026:04:09 22:30:03"})
        mock_image = mock_open.return_value.__enter__.return_value
        mock_image.getexif.return_value = fake_exif

        metadata = extract_photo_metadata(
            b'<x:xmpmeta><rdf:Description photoshop:DateCreated="2026-03-07T12:16:22" /></x:xmpmeta>'
        )

        self.assertEqual(metadata["taken_at"].year, 2026)
        self.assertEqual(metadata["taken_at"].month, 3)
        self.assertEqual(metadata["taken_at"].day, 7)


@override_settings(
    DROPBOX_APP_KEY="app-key",
    DROPBOX_APP_SECRET="app-secret",
    DROPBOX_REDIRECT_URI="http://127.0.0.1:8000/admin/dropbox-import/oauth/callback/",
    DROPBOX_TO_PUBLISH_FOLDER="/to-publish",
    DROPBOX_PUBLISHED_FOLDER="/published",
)
class ImporterViewMetadataTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.user)

        auth_state = DropboxAuthState.get_solo()
        auth_state.refresh_token = "refresh-token"
        auth_state.is_active = True
        auth_state.save()

    @patch("media_importer.services.importer.extract_photo_metadata")
    @patch("media_importer.views.DropboxClient")
    def test_imported_image_gets_dropbox_tag_and_icelandic_description(
        self,
        mock_dropbox_client,
        mock_extract_photo_metadata,
    ):
        mock_extract_photo_metadata.return_value = {
            "taken_at": timezone.make_aware(datetime(2023, 7, 14, 22, 5)),
            "camera_make": "FUJIFILM",
            "camera_model": "X-T4",
            "lens_model": "XF23mmF2 R WR",
            "focal_length_mm": "23.00",
            "shutter_speed": "1/160 sek",
            "aperture": "4.50",
            "iso": 1600,
            "gps": {
                "latitude": 65.68353,
                "longitude": -18.08780,
            },
        }
        client_instance = mock_dropbox_client.return_value
        file_info = SimpleNamespace(
            id="id-1",
            name="photo.jpg",
            path_lower="/to-publish/photo.jpg",
            path_display="/to-publish/photo.jpg",
            content_hash="hash-1",
            rev="rev-1",
            server_modified=timezone.make_aware(datetime(2024, 1, 2, 12, 0)),
            size=1234,
        )
        client_instance.list_image_files.return_value = [file_info]
        client_instance.download_file.return_value = self._build_test_image_bytes()
        client_instance.move_file.return_value = "/published/photo.jpg"

        response = self.client.post(
            reverse("dropbox_import"),
            {"selected_files": [file_info.path_display]},
            follow=True,
        )

        self.assertRedirects(response, reverse("dropbox_import"))
        image = get_image_model().objects.get(title="photo.jpg")
        self.assertIn("Import from Dropbox", list(image.tags.names()))
        self.assertEqual(
            image.description,
            "Ljósmynd tekin 14. júlí 2023 kl. 22:05. "
            "Staðsetning samkvæmt GPS-gögnum: 65.68353°N, 18.08780°V.",
        )
        self.assertEqual(image.camera_make, "FUJIFILM")
        self.assertEqual(image.camera_model, "X-T4")
        self.assertEqual(image.lens_model, "XF23mmF2 R WR")
        self.assertEqual(str(image.focal_length_mm), "23.00")
        self.assertEqual(image.shutter_speed, "1/160 sek")
        self.assertEqual(str(image.aperture), "4.50")
        self.assertEqual(image.iso, 1600)

    def _build_test_image_bytes(self):
        buffer = BytesIO()
        image = PILImage.new("RGB", (20, 20), color="red")
        image.save(buffer, format="JPEG")
        return buffer.getvalue()


class FakeExif:
    def __init__(self, values=None, ifd_values=None):
        self.values = values or {}
        self.ifd_values = ifd_values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def get_ifd(self, key):
        if key not in self.ifd_values:
            raise KeyError(key)
        return self.ifd_values[key]

    def __bool__(self):
        return bool(self.values or self.ifd_values)
