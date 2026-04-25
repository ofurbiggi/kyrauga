from django.core.exceptions import ValidationError

from blog.models import BlogIndexPage
from home.models import HomePage
from home.models import NavigationMenuItem, NavigationSettings

from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase


class HomeSetUpTests(WagtailPageTestCase):
    """
    Tests for basic page structure setup and HomePage creation.
    """

    def test_root_create(self):
        root_page = Page.objects.get(pk=1)
        self.assertIsNotNone(root_page)

    def test_homepage_create(self):
        root_page = Page.objects.get(pk=1)
        homepage = HomePage(title="Home")
        root_page.add_child(instance=homepage)
        self.assertTrue(HomePage.objects.filter(title="Home").exists())


class HomeTests(WagtailPageTestCase):
    """
    Tests for homepage functionality and rendering.
    """

    def setUp(self):
        """
        Create a homepage instance for testing.
        """
        root_page = Page.get_first_root_node()
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)
        self.site = Site.objects.get(is_default_site=True)
        self.site.hostname = "testsite"
        self.site.root_page = self.homepage
        self.site.save()

    def test_homepage_is_renderable(self):
        self.assertPageIsRenderable(self.homepage)

    def test_homepage_template_used(self):
        response = self.client.get(self.homepage.url)
        self.assertTemplateUsed(response, "home/home_page.html")


class NavigationSettingsTests(WagtailPageTestCase):
    def setUp(self):
        self.root_page = Page.get_first_root_node()
        self.homepage = HomePage(title="Home")
        self.root_page.add_child(instance=self.homepage)
        self.site = Site.objects.get(is_default_site=True)
        self.site.hostname = "navtest.local"
        self.site.root_page = self.homepage
        self.site.save()
        self.blog_index = self.homepage.add_child(instance=BlogIndexPage(title="Inside page"))
        self.navigation_settings = NavigationSettings.for_site(self.site)

    def test_navigation_item_requires_internal_page_or_external_url(self):
        item = NavigationMenuItem(
            navigation_settings=self.navigation_settings,
            label="Empty item",
        )

        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_header_renders_internal_page_link(self):
        NavigationMenuItem.objects.create(
            navigation_settings=self.navigation_settings,
            label="Inside",
            internal_page=self.blog_index,
            sort_order=1,
        )

        response = self.client.get(self.blog_index.url, HTTP_HOST=self.site.hostname)

        self.assertContains(response, 'href="/inside-page/"')
        self.assertContains(response, "Inside")

    def test_header_renders_external_url_link(self):
        NavigationMenuItem.objects.create(
            navigation_settings=self.navigation_settings,
            label="Archive",
            external_url="https://example.com/archive/",
            sort_order=1,
        )

        response = self.client.get(self.blog_index.url, HTTP_HOST=self.site.hostname)

        self.assertContains(response, 'href="https://example.com/archive/"')
        self.assertContains(response, "Archive")

    def test_header_include_handles_empty_navigation(self):
        response = self.client.get(self.blog_index.url, HTTP_HOST=self.site.hostname)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Navigation items can be added in Settings")
