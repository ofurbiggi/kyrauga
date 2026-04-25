from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from wagtail.models import Page, Site

from blog.models import BlogIndexPage
from home.models import HomePage


class AdminHomepageQuickActionsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.user)

        self.root_page = Page.get_first_root_node()
        self.home_page = HomePage.objects.first()
        if self.home_page is None:
            self.home_page = self.root_page.add_child(
                instance=HomePage(title="Home", slug="home")
            )

        self.site = Site.objects.get(is_default_site=True)
        self.site.hostname = "testserver"
        self.site.root_page = self.home_page
        self.site.save()

        self.blog_index_page = BlogIndexPage.objects.child_of(self.home_page).first()
        if self.blog_index_page is None:
            self.blog_index_page = self.home_page.add_child(
                instance=BlogIndexPage(title="Blog", slug="blog")
            )

    def test_admin_homepage_shows_blog_post_and_import_shortcuts(self):
        response = self.client.get(reverse("wagtailadmin_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quick actions")
        self.assertContains(response, "New blog post")
        self.assertContains(
            response,
            reverse(
                "wagtailadmin_pages:add",
                args=["blog", "blogpage", self.blog_index_page.pk],
            ),
        )
        self.assertContains(response, "Import images")
        self.assertContains(response, reverse("dropbox_import"))
