from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from wagtail import hooks
from wagtail.admin.ui.components import Component

from .models import BlogIndexPage, BlogPage


class AdminQuickActionsPanel(Component):
    name = "admin_quick_actions"
    template_name = "blog/wagtailadmin/home/quick_actions.html"
    order = 200

    def get_blog_index_page(self, parent_context):
        return BlogIndexPage.objects.filter(slug="blog").first()

    def get_context_data(self, parent_context):
        request = parent_context["request"]
        blog_index_page = self.get_blog_index_page(parent_context)
        links = []

        if (
            blog_index_page is not None
            and blog_index_page.permissions_for_user(request.user).can_add_subpage()
        ):
            links.append(
                {
                    "label": _("New blog post"),
                    "description": _("Create a new blog post under /blog."),
                    "url": reverse(
                        "wagtailadmin_pages:add",
                        args=[
                            BlogPage._meta.app_label,
                            BlogPage._meta.model_name,
                            blog_index_page.pk,
                        ],
                    ),
                    "icon_name": "doc-empty-inverse",
                }
            )

        links.append(
            {
                "label": _("Import images"),
                "description": _("Open the Dropbox image import view."),
                "url": reverse("dropbox_import"),
                "icon_name": "image",
            }
        )

        return {
            "links": links,
        }

    def render_html(self, parent_context=None):
        if not self.get_context_data(parent_context)["links"]:
            return ""
        return super().render_html(parent_context)


@hooks.register("construct_homepage_panels")
def add_admin_quick_actions_panel(request, panels):
    panels.append(AdminQuickActionsPanel())
