import logging
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.apps import apps
from django.utils import timezone
from PIL import ExifTags, Image as PILImage


logger = logging.getLogger(__name__)

DROPBOX_IMPORT_TAG = "Import from Dropbox"
NORMAL_IMPORT_TAG = "Normal import"
METADATA_FIELD_NAMES = (
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
ICELANDIC_MONTH_NAMES = {
    1: "janúar",
    2: "febrúar",
    3: "mars",
    4: "apríl",
    5: "maí",
    6: "júní",
    7: "júlí",
    8: "ágúst",
    9: "september",
    10: "október",
    11: "nóvember",
    12: "desember",
}

GPS_TAG = next(key for key, value in ExifTags.TAGS.items() if value == "GPSInfo")
EXIF_IFD_TAG = next(key for key, value in ExifTags.TAGS.items() if value == "ExifOffset")
EXIF_TAGS_BY_NAME = {value: key for key, value in ExifTags.TAGS.items()}
GPS_TAGS_BY_ID = ExifTags.GPSTAGS
XMP_PATTERNS = {
    "camera_make": [
        r'tiff:Make="([^"]+)"',
    ],
    "camera_model": [
        r'tiff:Model="([^"]+)"',
    ],
    "lens_model": [
        r'exifEX:LensModel="([^"]+)"',
        r'aux:Lens="([^"]+)"',
    ],
    "taken_at": [
        r'photoshop:DateCreated="([^"]+)"',
        r'exif:DateTimeOriginal="([^"]+)"',
    ],
    "focal_length_text": [
        r'exif:FocalLength="([^"]+)"',
    ],
    "aperture_text": [
        r'exif:FNumber="([^"]+)"',
    ],
    "shutter_speed": [
        r'exif:ExposureTime="([^"]+)"',
    ],
    "iso_text": [
        r'exif:ISOSpeedRatings="([^"]+)"',
    ],
    "lens_info": [
        r'aux:LensInfo="([^"]+)"',
    ],
}


def apply_import_metadata(
    image,
    file_bytes,
    file_info,
    description_override="",
    metadata=None,
    user=None,
):
    metadata = metadata or extract_photo_metadata(file_bytes)
    update_image_metadata(
        image,
        metadata,
        description=description_override or build_icelandic_description(metadata, file_info=file_info),
        tag_name=DROPBOX_IMPORT_TAG,
        history_source="dropbox",
        user=user,
    )
    logger.info(
        "Applied import metadata to image",
        extra={
            "image_id": image.pk,
            "image_title": image.title,
            "dropbox_path": getattr(file_info, "path_display", ""),
            "has_taken_at": bool(metadata.get("taken_at")),
            "has_gps": bool(metadata.get("gps")),
            "camera_model": metadata.get("camera_model", ""),
            "lens_model": metadata.get("lens_model", ""),
        },
    )


def apply_uploaded_image_metadata(image, user=None):
    metadata = extract_photo_metadata(read_image_file_bytes(image))
    description = ""
    if not (image.description or "").strip():
        description = build_icelandic_description(
            metadata,
            fallback_text="Innflutt mynd.",
        )

    update_image_metadata(
        image,
        metadata,
        description=description,
        tag_name=NORMAL_IMPORT_TAG,
        history_source="normal",
        user=user,
    )


def apply_structured_metadata(image, metadata):
    gps = metadata.get("gps") or {}
    image.taken_at = metadata.get("taken_at")
    image.camera_make = metadata.get("camera_make", "")
    image.camera_model = metadata.get("camera_model", "")
    image.lens_model = metadata.get("lens_model", "")
    image.focal_length_mm = metadata.get("focal_length_mm")
    image.shutter_speed = metadata.get("shutter_speed", "")
    image.aperture = metadata.get("aperture")
    image.iso = metadata.get("iso")
    image.gps_latitude = gps.get("latitude")
    image.gps_longitude = gps.get("longitude")
    image.location_name = metadata.get("location_name", "")
    image.location_city = metadata.get("location_city", "")
    image.location_country = metadata.get("location_country", "")


def build_image_metadata_snapshot(image):
    return {
        "taken_at": image.taken_at.isoformat() if image.taken_at else None,
        "camera_make": image.camera_make or "",
        "camera_model": image.camera_model or "",
        "lens_model": image.lens_model or "",
        "focal_length_mm": str(image.focal_length_mm) if image.focal_length_mm is not None else None,
        "shutter_speed": image.shutter_speed or "",
        "aperture": str(image.aperture) if image.aperture is not None else None,
        "iso": image.iso,
        "gps_latitude": str(image.gps_latitude) if image.gps_latitude is not None else None,
        "gps_longitude": str(image.gps_longitude) if image.gps_longitude is not None else None,
        "location_name": image.location_name or "",
        "location_city": image.location_city or "",
        "location_country": image.location_country or "",
    }


def build_metadata_changes(before, after):
    changes = {}
    for field_name in METADATA_FIELD_NAMES:
        if before.get(field_name) != after.get(field_name):
            changes[field_name] = {
                "before": before.get(field_name),
                "after": after.get(field_name),
            }
    return changes


def create_metadata_history(image, source, user=None, changes=None):
    history_model = apps.get_model("media_importer", "ImageMetadataHistory")
    return history_model.objects.create(
        image=image,
        source=source,
        user=user if getattr(user, "is_authenticated", False) else None,
        changes=changes or {},
    )


def update_image_metadata(
    image,
    metadata,
    *,
    description="",
    tag_name="",
    history_source=None,
    user=None,
):
    before = build_image_metadata_snapshot(image)
    apply_structured_metadata(image, metadata)
    if description:
        image.description = description
    image.save(
        update_fields=[
            *METADATA_FIELD_NAMES,
            *(["description"] if description else []),
        ]
    )

    if tag_name:
        image.tags.add(tag_name)

    changes = build_metadata_changes(before, build_image_metadata_snapshot(image))
    if history_source:
        create_metadata_history(
            image,
            source=history_source,
            user=user,
            changes=changes,
        )


def read_image_file_bytes(image):
    image.file.open("rb")
    try:
        return image.file.read()
    finally:
        image.file.close()


def extract_photo_metadata(file_bytes):
    try:
        with PILImage.open(BytesIO(file_bytes)) as image:
            exif = image.getexif()
    except Exception:
        logger.exception("Failed to open image while extracting photo metadata")
        return {}

    if not exif:
        logger.debug("Image had no EXIF metadata")
        return {}

    metadata = {}

    exif_ifd = _extract_exif_ifd(exif)

    taken_at = _extract_taken_at(exif, exif_ifd=exif_ifd)
    if taken_at:
        metadata["taken_at"] = taken_at

    for field_name, metadata_key in (
        ("Make", "camera_make"),
        ("Model", "camera_model"),
        ("LensModel", "lens_model"),
    ):
        value = _extract_string(_get_exif_value(exif, field_name, exif_ifd=exif_ifd))
        if value:
            metadata[metadata_key] = value

    focal_length = _extract_decimal(_get_exif_value(exif, "FocalLength", exif_ifd=exif_ifd))
    if focal_length is not None:
        metadata["focal_length_mm"] = focal_length

    aperture = _extract_decimal(_get_exif_value(exif, "FNumber", exif_ifd=exif_ifd))
    if aperture is not None:
        metadata["aperture"] = aperture

    shutter_speed = _extract_shutter_speed(exif, exif_ifd=exif_ifd)
    if shutter_speed:
        metadata["shutter_speed"] = shutter_speed

    iso = _extract_iso(exif, exif_ifd=exif_ifd)
    if iso is not None:
        metadata["iso"] = iso

    gps = _extract_gps(exif)
    if gps:
        metadata["gps"] = gps

    xmp_metadata = extract_xmp_metadata(file_bytes)
    for key, value in xmp_metadata.items():
        metadata.setdefault(key, value)

    logger.debug(
        "Extracted photo metadata",
        extra={
            "metadata_keys": sorted(metadata.keys()),
            "has_taken_at": bool(metadata.get("taken_at")),
            "has_gps": bool(metadata.get("gps")),
        },
    )
    return metadata


def build_icelandic_description(metadata, file_info=None, fallback_text="Innflutt mynd úr Dropbox."):
    segments = []
    taken_at = metadata.get("taken_at")
    gps = metadata.get("gps")
    location_name = metadata.get("location_name")
    location_city = metadata.get("location_city")
    location_country = metadata.get("location_country")

    if taken_at:
        segments.append(f"Ljósmynd tekin {format_icelandic_datetime(taken_at)}.")
    elif getattr(file_info, "server_modified", None):
        segments.append(
            f"Skráin var síðast dagsett í Dropbox {format_icelandic_datetime(file_info.server_modified)}."
        )
    else:
        segments.append(fallback_text)

    location_parts = [part for part in [location_name, location_city, location_country] if part]
    if location_parts:
        segments.append(f"Staðsetning: {', '.join(location_parts)}.")
    elif gps:
        segments.append(
            "Staðsetning samkvæmt GPS-gögnum: "
            f"{format_icelandic_coordinates(gps['latitude'], gps['longitude'])}."
        )

    return " ".join(segments)




def format_icelandic_datetime(value):
    month = ICELANDIC_MONTH_NAMES[value.month]
    return f"{value.day}. {month} {value.year} kl. {value:%H:%M}"


def format_icelandic_coordinates(latitude, longitude):
    lat_direction = "N" if latitude >= 0 else "S"
    lon_direction = "A" if longitude >= 0 else "V"
    return (
        f"{abs(latitude):.5f}°{lat_direction}, "
        f"{abs(longitude):.5f}°{lon_direction}"
    )


def _extract_exif_ifd(exif):
    try:
        return exif.get_ifd(EXIF_IFD_TAG)
    except Exception:
        return {}


def _get_exif_value(exif, field_name, exif_ifd=None):
    tag_id = EXIF_TAGS_BY_NAME.get(field_name)
    if tag_id is None:
        return None

    value = exif.get(tag_id)
    if value is not None:
        return value

    if exif_ifd and tag_id in exif_ifd:
        return exif_ifd.get(tag_id)

    return None


def _extract_taken_at(exif, exif_ifd=None):
    for field_name in ("DateTimeOriginal", "DateTimeDigitized"):
        raw_value = _get_exif_value(exif, field_name, exif_ifd=exif_ifd)
        parsed = _parse_exif_datetime(raw_value)
        if parsed:
            return parsed
    return None


def _extract_string(value):
    if not value:
        return ""

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")

    return str(value).strip()


def _extract_decimal(value):
    if value is None or value == "":
        return None

    try:
        return Decimal(str(_rational_to_float(value))).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError, ZeroDivisionError):
        return None


def _extract_iso(exif, exif_ifd=None):
    for field_name in ("PhotographicSensitivity", "ISOSpeedRatings"):
        value = _get_exif_value(exif, field_name, exif_ifd=exif_ifd)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0]
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _extract_shutter_speed(exif, exif_ifd=None):
    exposure_time = _get_exif_value(exif, "ExposureTime", exif_ifd=exif_ifd)
    if exposure_time:
        rendered = _format_fraction(exposure_time)
        if rendered:
            return rendered

    shutter_speed_value = _get_exif_value(exif, "ShutterSpeedValue", exif_ifd=exif_ifd)
    if shutter_speed_value is None:
        return ""

    try:
        shutter_seconds = 1 / (2 ** _rational_to_float(shutter_speed_value))
    except Exception:
        return ""

    return _format_seconds(shutter_seconds)


def _parse_exif_datetime(raw_value):
    if not raw_value:
        return None

    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8", errors="ignore")

    try:
        parsed = datetime.strptime(str(raw_value), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _extract_gps(exif):
    gps_info = exif.get(GPS_TAG)
    if isinstance(gps_info, Mapping):
        gps_source = gps_info
    elif hasattr(exif, "get_ifd"):
        try:
            gps_source = exif.get_ifd(GPS_TAG)
        except KeyError:
            gps_source = None
        except Exception:
            logger.exception("Failed to read GPS IFD from EXIF metadata")
            gps_source = None
    else:
        gps_source = None

    if not gps_source:
        return None

    if not isinstance(gps_source, Mapping):
        logger.warning(
            "Skipping GPS metadata because EXIF GPS payload was not a mapping",
            extra={"gps_type": type(gps_source).__name__},
        )
        return None

    gps_map = {
        GPS_TAGS_BY_ID.get(key, key): value
        for key, value in gps_source.items()
    }

    latitude = _convert_gps_coordinate(
        gps_map.get("GPSLatitude"),
        gps_map.get("GPSLatitudeRef"),
    )
    longitude = _convert_gps_coordinate(
        gps_map.get("GPSLongitude"),
        gps_map.get("GPSLongitudeRef"),
    )

    if latitude is None or longitude is None:
        return None

    return {
        "latitude": latitude,
        "longitude": longitude,
    }


def extract_xmp_metadata(file_bytes):
    try:
        raw_text = file_bytes.decode("latin1", errors="ignore")
    except Exception:
        return {}

    metadata = {}

    for key, patterns in XMP_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, raw_text)
            if match:
                metadata[key] = match.group(1).strip()
                break

    if "taken_at" in metadata:
        parsed = _parse_xmp_datetime(metadata["taken_at"])
        if parsed:
            metadata["taken_at"] = parsed
        else:
            metadata.pop("taken_at", None)

    if "focal_length_text" in metadata:
        focal_length = _extract_decimal(metadata["focal_length_text"])
        if focal_length is not None:
            metadata["focal_length_mm"] = focal_length

    if "aperture_text" in metadata:
        aperture = _extract_decimal(metadata["aperture_text"])
        if aperture is not None:
            metadata["aperture"] = aperture

    if "iso_text" in metadata:
        try:
            metadata["iso"] = int(float(metadata["iso_text"]))
        except (TypeError, ValueError):
            pass

    if "lens_info" in metadata:
        lens_info = _parse_lens_info(metadata["lens_info"])
        if lens_info.get("focal_length_mm") is not None:
            metadata.setdefault("focal_length_mm", lens_info["focal_length_mm"])
        if lens_info.get("aperture") is not None:
            metadata.setdefault("aperture", lens_info["aperture"])

    if "lens_model" in metadata:
        lens_model_values = _parse_lens_model_values(metadata["lens_model"])
        if lens_model_values.get("focal_length_mm") is not None:
            metadata.setdefault("focal_length_mm", lens_model_values["focal_length_mm"])
        if lens_model_values.get("aperture") is not None:
            metadata.setdefault("aperture", lens_model_values["aperture"])

    metadata.pop("focal_length_text", None)
    metadata.pop("aperture_text", None)
    metadata.pop("iso_text", None)
    metadata.pop("lens_info", None)

    return metadata


def _convert_gps_coordinate(values, reference):
    if not values or not reference:
        return None

    reference = reference.decode("utf-8", errors="ignore") if isinstance(reference, bytes) else str(reference)

    try:
        degrees, minutes, seconds = values
        coordinate = (
            _rational_to_float(degrees)
            + _rational_to_float(minutes) / 60
            + _rational_to_float(seconds) / 3600
        )
    except Exception:
        return None

    if reference in {"S", "W"}:
        coordinate *= -1

    return coordinate


def _rational_to_float(value):
    if isinstance(value, str):
        value = value.strip()
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            if float(denominator) == 0:
                raise ZeroDivisionError("Rational metadata value had a zero denominator")
            return float(numerator) / float(denominator)
        return float(value)

    if isinstance(value, tuple):
        numerator, denominator = value
        if float(denominator) == 0:
            raise ZeroDivisionError("Rational metadata value had a zero denominator")
        return float(numerator) / float(denominator)

    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        if float(value.denominator) == 0:
            raise ZeroDivisionError("Rational metadata value had a zero denominator")
        return float(value.numerator) / float(value.denominator)

    return float(value)


def _format_fraction(value):
    if isinstance(value, tuple):
        numerator, denominator = value
        if denominator:
            return _format_seconds(float(numerator) / float(denominator))

    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        if value.denominator:
            return _format_seconds(float(value.numerator) / float(value.denominator))

    try:
        return _format_seconds(float(value))
    except (TypeError, ValueError):
        return ""


def _format_seconds(seconds):
    if seconds <= 0:
        return ""
    if seconds >= 1:
        return f"{seconds:.1f} sek"

    denominator = round(1 / seconds)
    if denominator:
        approx_seconds = 1 / denominator
        if abs(approx_seconds - seconds) < 0.02:
            return f"1/{denominator} sek"

    return f"{seconds:.3f} sek"


def _parse_xmp_datetime(value):
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_lens_info(value):
    parts = str(value).split()
    if len(parts) != 4:
        return {}

    parsed = []
    for part in parts:
        decimal_value = _extract_decimal(part)
        if decimal_value is None:
            return {}
        parsed.append(decimal_value)

    min_focal, max_focal, min_aperture, max_aperture = parsed
    result = {}
    if min_focal == max_focal:
        result["focal_length_mm"] = min_focal
    if min_aperture == max_aperture:
        result["aperture"] = min_aperture
    return result


def _parse_lens_model_values(value):
    text = str(value)
    result = {}

    focal_match = re.search(r"(\d+(?:\.\d+)?)\s*mm", text, re.IGNORECASE)
    if focal_match:
        focal_length = _extract_decimal(focal_match.group(1))
        if focal_length is not None:
            result["focal_length_mm"] = focal_length

    aperture_match = re.search(r"f/\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if aperture_match:
        aperture = _extract_decimal(aperture_match.group(1))
        if aperture is not None:
            result["aperture"] = aperture

    return result
