from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import ExifTags, Image as PILImage
from wagtail.images import get_image_model
from wagtail.models import Collection

from media_importer.models import ImageMetadataHistory


def make_test_image_file(name="photo.jpg", color=(20, 40, 60)):
    buffer = BytesIO()
    image = PILImage.new("RGB", (1200, 800), color)
    image.save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def make_exif_test_image_file(name="photo-exif.jpg", color=(20, 40, 60)):
    tag_ids = {value: key for key, value in ExifTags.TAGS.items()}
    buffer = BytesIO()
    image = PILImage.new("RGB", (1200, 800), color)
    exif = PILImage.Exif()
    exif[tag_ids["DateTimeOriginal"]] = "2026:04:09 22:30:03"
    exif[tag_ids["Make"]] = "FUJIFILM"
    exif[tag_ids["Model"]] = "X-T4"
    exif[tag_ids["LensModel"]] = "XF23mmF2 R WR"
    exif[tag_ids["FocalLength"]] = (23, 1)
    exif[tag_ids["FNumber"]] = (45, 10)
    exif[tag_ids["ExposureTime"]] = (1, 160)
    exif[tag_ids["ISOSpeedRatings"]] = 1600
    image.save(buffer, format="JPEG", exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def metadata_payload():
    return {
        "taken_at": timezone.make_aware(datetime(2023, 7, 14, 22, 5)),
        "camera_make": "FUJIFILM",
        "camera_model": "X-T4",
        "lens_model": "XF23mmF2 R WR",
        "focal_length_mm": Decimal("23.00"),
        "shutter_speed": "1/160 sek",
        "aperture": Decimal("4.50"),
        "iso": 1600,
        "gps": {
            "latitude": Decimal("65.683530"),
            "longitude": Decimal("-18.087800"),
        },
        "location_name": "Akureyri",
        "location_city": "Akureyri",
        "location_country": "Iceland",
    }


class WagtailImageUploadMetadataTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.user)
        self.collection = Collection.get_first_root_node()
        self.image_model = get_image_model()

    def create_image(self, **kwargs):
        defaults = {
            "title": "Existing image",
            "file": make_test_image_file("existing.jpg"),
            "collection": self.collection,
        }
        defaults.update(kwargs)
        return self.image_model.objects.create(**defaults)

    def assert_metadata_applied(self, image):
        image.refresh_from_db()
        self.assertEqual(image.camera_make, "FUJIFILM")
        self.assertEqual(image.camera_model, "X-T4")
        self.assertEqual(image.lens_model, "XF23mmF2 R WR")
        self.assertEqual(str(image.focal_length_mm), "23.00")
        self.assertEqual(image.shutter_speed, "1/160 sek")
        self.assertEqual(str(image.aperture), "4.50")
        self.assertEqual(image.iso, 1600)
        self.assertEqual(str(image.gps_latitude), "65.683530")
        self.assertEqual(str(image.gps_longitude), "-18.087800")
        self.assertEqual(image.location_name, "Akureyri")
        self.assertEqual(image.location_city, "Akureyri")
        self.assertEqual(image.location_country, "Iceland")
        self.assertIn("Normal import", list(image.tags.names()))
        self.assertEqual(
            image.description,
            "Ljósmynd tekin 14. júlí 2023 kl. 22:05. Staðsetning: Akureyri, Akureyri, Iceland.",
        )

    @patch("media_importer.services.importer.extract_photo_metadata", return_value=metadata_payload())
    def test_normal_wagtail_image_upload_triggers_metadata_extraction(self, mock_extract_metadata):
        response = self.client.post(
            reverse("wagtailimages:add"),
            {
                "title": "Normal upload",
                "collection": self.collection.id,
                "file": make_test_image_file("normal-upload.jpg"),
                "description": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        image = self.image_model.objects.get(title="Normal upload")
        self.assert_metadata_applied(image)
        mock_extract_metadata.assert_called_once()

        history = image.metadata_history.get()
        self.assertEqual(history.source, ImageMetadataHistory.SOURCE_NORMAL)
        self.assertEqual(history.user, self.user)
        self.assertIn("camera_make", history.changes)

    def test_normal_upload_with_real_exif_file_persists_metadata_fields(self):
        response = self.client.post(
            reverse("wagtailimages:add"),
            {
                "title": "Real EXIF upload",
                "collection": self.collection.id,
                "file": make_exif_test_image_file("real-exif-upload.jpg"),
                "description": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        image = self.image_model.objects.get(title="Real EXIF upload")
        self.assertEqual(image.camera_make, "FUJIFILM")
        self.assertEqual(image.camera_model, "X-T4")
        self.assertEqual(image.lens_model, "XF23mmF2 R WR")
        self.assertEqual(str(image.focal_length_mm), "23.00")
        self.assertEqual(image.shutter_speed, "1/160 sek")
        self.assertEqual(str(image.aperture), "4.50")
        self.assertEqual(image.iso, 1600)

    @patch("media_importer.services.importer.extract_photo_metadata", return_value=metadata_payload())
    def test_bulk_upload_triggers_metadata_extraction(self, mock_extract_metadata):
        response = self.client.post(
            reverse("wagtailimages:add_multiple"),
            {
                "title": "Bulk upload",
                "collection": self.collection.id,
                "files[]": make_test_image_file("bulk-upload.jpg"),
            },
        )

        self.assertEqual(response.status_code, 200)
        image = self.image_model.objects.get(title="Bulk upload")
        self.assert_metadata_applied(image)
        mock_extract_metadata.assert_called_once()

    @patch("media_importer.services.importer.extract_photo_metadata", return_value=metadata_payload())
    def test_chooser_upload_triggers_metadata_extraction(self, mock_extract_metadata):
        response = self.client.post(
            reverse("wagtailimages_chooser:create"),
            {
                "image-chooser-upload-title": "Chooser upload",
                "image-chooser-upload-collection": self.collection.id,
                "image-chooser-upload-file": make_test_image_file("chooser-upload.jpg"),
                "image-chooser-upload-description": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        image = self.image_model.objects.get(title="Chooser upload")
        self.assert_metadata_applied(image)
        mock_extract_metadata.assert_called_once()

    @patch("media_importer.services.importer.extract_photo_metadata", return_value={})
    def test_image_with_no_exif_leaves_metadata_fields_blank(self, mock_extract_metadata):
        response = self.client.post(
            reverse("wagtailimages:add"),
            {
                "title": "Blank metadata upload",
                "collection": self.collection.id,
                "file": make_test_image_file("blank-metadata.jpg"),
                "description": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        image = self.image_model.objects.get(title="Blank metadata upload")
        self.assertEqual(image.camera_make, "")
        self.assertIsNone(image.taken_at)
        self.assertIsNone(image.gps_latitude)
        self.assertEqual(image.description, "Innflutt mynd.")
        self.assertIn("Normal import", list(image.tags.names()))
        self.assertEqual(image.metadata_history.count(), 1)
        mock_extract_metadata.assert_called_once()

    @patch("media_importer.services.importer.extract_photo_metadata")
    def test_image_replacement_does_not_trigger_metadata_extraction(self, mock_extract_metadata):
        image = self.create_image(
            camera_make="Original make",
            description="Original description",
        )

        response = self.client.post(
            reverse("wagtailimages:edit", args=[image.pk]),
            {
                "title": image.title,
                "collection": self.collection.id,
                "description": image.description,
                "file": make_test_image_file("replacement.jpg", color=(10, 20, 30)),
                "taken_at": "",
                "camera_make": image.camera_make,
                "camera_model": "",
                "lens_model": "",
                "focal_length_mm": "",
                "shutter_speed": "",
                "aperture": "",
                "iso": "",
                "gps_latitude": "",
                "gps_longitude": "",
                "location_name": "",
                "location_city": "",
                "location_country": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        image.refresh_from_db()
        self.assertEqual(image.camera_make, "Original make")
        mock_extract_metadata.assert_not_called()
        self.assertFalse(image.tags.filter(name="Normal import").exists())


class WagtailImageAdminMetadataEditingTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.user)
        self.collection = Collection.get_first_root_node()
        self.image_model = get_image_model()

    def create_image(self, **kwargs):
        defaults = {
            "title": "Editable image",
            "file": make_test_image_file("editable.jpg"),
            "collection": self.collection,
            "description": "Existing description",
        }
        defaults.update(kwargs)
        return self.image_model.objects.create(**defaults)

    def build_edit_payload(self, image, **overrides):
        payload = {
            "title": image.title,
            "collection": self.collection.id,
            "description": image.description,
            "taken_at": "",
            "camera_make": image.camera_make,
            "camera_model": image.camera_model,
            "lens_model": image.lens_model,
            "focal_length_mm": image.focal_length_mm or "",
            "shutter_speed": image.shutter_speed,
            "aperture": image.aperture or "",
            "iso": image.iso or "",
            "gps_latitude": image.gps_latitude or "",
            "gps_longitude": image.gps_longitude or "",
            "location_name": image.location_name,
            "location_city": image.location_city,
            "location_country": image.location_country,
        }
        payload.update(overrides)
        return payload

    def test_metadata_fields_can_be_saved_from_edit_page_and_record_history(self):
        image = self.create_image()

        response = self.client.post(
            reverse("wagtailimages:edit", args=[image.pk]),
            self.build_edit_payload(
                image,
                taken_at="2024-07-14T22:05",
                camera_make="FUJIFILM",
                camera_model="X-T4",
                lens_model="XF23mmF2 R WR",
                focal_length_mm="23.00",
                shutter_speed="1/160 sek",
                aperture="4.50",
                iso="1600",
                gps_latitude="65.683530",
                gps_longitude="-18.087800",
                location_name="Akureyri",
                location_city="Akureyri",
                location_country="Iceland",
            ),
        )

        self.assertEqual(response.status_code, 302)
        image.refresh_from_db()
        self.assertEqual(image.camera_make, "FUJIFILM")
        self.assertEqual(str(image.gps_latitude), "65.683530")

        history = image.metadata_history.get()
        self.assertEqual(history.source, ImageMetadataHistory.SOURCE_MANUAL)
        self.assertEqual(history.user, self.user)
        self.assertIn("gps_latitude", history.changes)

    def test_metadata_fields_can_be_cleared(self):
        image = self.create_image(
            camera_make="FUJIFILM",
            camera_model="X-T4",
            gps_latitude=Decimal("65.683530"),
            gps_longitude=Decimal("-18.087800"),
        )

        response = self.client.post(
            reverse("wagtailimages:edit", args=[image.pk]),
            self.build_edit_payload(
                image,
                camera_make="",
                camera_model="",
                gps_latitude="",
                gps_longitude="",
            ),
        )

        self.assertEqual(response.status_code, 302)
        image.refresh_from_db()
        self.assertEqual(image.camera_make, "")
        self.assertEqual(image.camera_model, "")
        self.assertIsNone(image.gps_latitude)
        self.assertIsNone(image.gps_longitude)

    def test_admin_page_renders_leaflet_map_and_existing_coordinates(self):
        image = self.create_image(
            gps_latitude=Decimal("65.683530"),
            gps_longitude=Decimal("-18.087800"),
        )

        response = self.client.get(reverse("wagtailimages:edit", args=[image.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "leaflet.js")
        self.assertContains(response, 'data-kyrauga-gps-map')
        self.assertContains(response, 'data-latitude="65.683530"')
        self.assertContains(response, 'data-longitude="-18.087800"')
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertNotEqual(response.headers.get("Referrer-Policy"), "no-referrer")

    def test_admin_page_renders_blank_map_state_without_crashing(self):
        image = self.create_image()

        response = self.client.get(reverse("wagtailimages:edit", args=[image.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-kyrauga-gps-map')
        self.assertContains(response, 'data-latitude=""')
        self.assertContains(response, 'data-longitude=""')

    def test_admin_map_script_uses_canonical_osm_tile_url_and_referrer_policy(self):
        script_path = Path(__file__).resolve().parents[2] / "config" / "static" / "js" / "kyrauga-image-metadata-map.js"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", script)
        self.assertIn('referrerPolicy: "strict-origin-when-cross-origin"', script)
        self.assertNotIn("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", script)
