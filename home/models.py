from django.core.exceptions import ValidationError
from django.db import models

from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.models import Page
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.models import Orderable


class HomePage(Page):
    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        from blog.models import BlogIndexPage

        blog_index_page = (
            BlogIndexPage.objects.child_of(self)
            .live()
            .public()
            .first()
        )
        context["blog_index_page"] = blog_index_page
        context["pinned_items"] = blog_index_page.get_pinned_items() if blog_index_page else []
        return context


@register_setting
class NavigationSettings(ClusterableModel, BaseSiteSetting):
    panels = [
        MultiFieldPanel(
            [
                InlinePanel("menu_items", label="Menu item"),
            ],
            heading="Global site navigation",
        ),
    ]


class NavigationMenuItem(Orderable):
    navigation_settings = ParentalKey(
        "home.NavigationSettings",
        on_delete=models.CASCADE,
        related_name="menu_items",
    )
    label = models.CharField(max_length=100)
    internal_page = models.ForeignKey(
        "wagtailcore.Page",
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
    )
    external_url = models.URLField(blank=True)

    panels = [
        FieldPanel("label"),
        FieldPanel("internal_page"),
        FieldPanel("external_url"),
    ]

    class Meta(Orderable.Meta):
        ordering = ["sort_order", "id"]

    def clean(self):
        super().clean()

        if not self.internal_page and not self.external_url:
            raise ValidationError(
                {"internal_page": "Choose an internal page or enter an external URL."}
            )

    @property
    def url(self):
        if self.internal_page:
            return self.internal_page.url
        return self.external_url
