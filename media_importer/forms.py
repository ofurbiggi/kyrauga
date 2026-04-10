from django import forms
from wagtail.images.forms import BaseImageForm


class CustomImageForm(BaseImageForm):
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
            }
        ),
    )

