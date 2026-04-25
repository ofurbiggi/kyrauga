from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomImage
from .services.importer import apply_uploaded_image_metadata


@receiver(post_save, sender=CustomImage)
def populate_metadata_for_new_wagtail_upload(sender, instance, created, raw, **kwargs):
    if raw or not created:
        return

    if getattr(instance, "_metadata_upload_source", "") != "normal":
        return

    if getattr(instance, "_skip_upload_metadata_signal", False):
        return

    apply_uploaded_image_metadata(
        instance,
        user=getattr(instance, "_metadata_user", None),
    )
