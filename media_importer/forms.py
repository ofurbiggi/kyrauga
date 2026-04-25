from django import forms
from wagtail.images.forms import BaseImageForm

from .services.importer import (
    METADATA_FIELD_NAMES,
    apply_uploaded_image_metadata,
    build_image_metadata_snapshot,
    build_metadata_changes,
    create_metadata_history,
)


class CustomImageForm(BaseImageForm):
    metadata_field_names = METADATA_FIELD_NAMES

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, user=user, **kwargs)

        self.fields["taken_at"].widget = forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        )
        self.fields["taken_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            *self.fields["taken_at"].input_formats,
        ]
        self.fields["gps_latitude"].widget.attrs.update(
            {
                "step": "any",
                "data-kyrauga-gps-target": "latitude",
            }
        )
        self.fields["gps_longitude"].widget.attrs.update(
            {
                "step": "any",
                "data-kyrauga-gps-target": "longitude",
            }
        )

    @property
    def non_metadata_fields(self):
        return [
            field
            for field in self.visible_fields()
            if field.name not in self.metadata_field_names
        ]

    @property
    def metadata_fields(self):
        return [self[name] for name in self.metadata_field_names]

    def save(self, commit=True):
        before = None
        should_track_manual_history = bool(self.instance.pk)
        if should_track_manual_history:
            before = build_image_metadata_snapshot(
                type(self.instance).objects.get(pk=self.instance.pk)
            )

        instance = super().save(commit=False)
        instance._metadata_user = self.user
        if instance._state.adding:
            if commit:
                instance._skip_upload_metadata_signal = True
            else:
                instance._metadata_upload_source = "normal"

        if commit:
            instance.save()
            self.save_m2m()

            if should_track_manual_history:
                changed_fields = [
                    field_name
                    for field_name in self.metadata_field_names
                    if field_name in self.changed_data
                ]
                if changed_fields:
                    after = build_image_metadata_snapshot(instance)
                    changes = {
                        field_name: value
                        for field_name, value in build_metadata_changes(before, after).items()
                        if field_name in changed_fields
                    }
                    if changes:
                        create_metadata_history(
                            instance,
                            source="manual",
                            user=self.user,
                            changes=changes,
                        )

            if not should_track_manual_history and getattr(instance, "_skip_upload_metadata_signal", False):
                apply_uploaded_image_metadata(instance, user=self.user)

        return instance
