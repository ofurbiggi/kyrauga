from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from wagtail.models import Page, Site

from blog.models import BlogIndexPage, BlogIndexPagePinnedItem, BlogPage, PhotoSeriesPage
from home.models import HomePage
from media_importer.models import CustomImage


def make_test_image_file(name="test.jpg", color=(20, 40, 60)):
    buffer = BytesIO()
    image = Image.new("RGB", (1200, 800), color)
    image.save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class BlogPageModelTests(TestCase):
    def setUp(self):
        self.root_page = Page.get_first_root_node()
        self.home_page = HomePage.objects.first()
        if self.home_page is None:
            self.home_page = self.root_page.add_child(instance=HomePage(title="Home", slug="home"))
        self.site = Site.objects.get(is_default_site=True)
        self.site.hostname = "testserver"
        self.site.root_page = self.home_page
        self.site.save()
        self.index_page = self.home_page.add_child(instance=BlogIndexPage(title="Blog", slug="blog"))
        self.request_factory = RequestFactory()

    def make_image(self, **kwargs):
        defaults = {
            "title": kwargs.pop("title", "Test image"),
            "file": make_test_image_file(kwargs.pop("filename", "test.jpg")),
            "description": kwargs.pop("description", "Image description"),
        }
        defaults.update(kwargs)
        return CustomImage.objects.create(**defaults)

    def make_blog_page(self, title="A blog post", slug="a-blog-post", **kwargs):
        featured_image = kwargs.pop("featured_image", self.make_image())
        display_date = kwargs.pop("display_date", timezone.make_aware(datetime(2026, 1, 15, 12, 0, 0)))
        blog_page = BlogPage(
            title=title,
            slug=slug,
            featured_image=featured_image,
            display_date=display_date,
            caption=kwargs.pop("caption", ""),
            manual_latitude=kwargs.pop("manual_latitude", None),
            manual_longitude=kwargs.pop("manual_longitude", None),
            body=kwargs.pop("body", []),
            **kwargs,
        )
        self.index_page.add_child(instance=blog_page)
        blog_page.save_revision().publish()
        return BlogPage.objects.get(pk=blog_page.pk)

    def make_series(self, title="Series", slug="series"):
        series_page = PhotoSeriesPage(title=title, slug=slug)
        self.index_page.add_child(instance=series_page)
        series_page.save_revision().publish()
        return PhotoSeriesPage.objects.get(pk=series_page.pk)

    def get_index_context(self, query_string=""):
        request = self.request_factory.get(f"/blog/{query_string}")
        request.site = self.site
        return self.index_page.get_context(request)

    def make_chronological_blog_pages(self, count):
        base_published_at = timezone.make_aware(datetime(2026, 1, 1, 12, 0, 0))
        pages = []
        for number in range(count):
            page = self.make_blog_page(title=f"Post {number}", slug=f"post-{number}")
            BlogPage.objects.filter(pk=page.pk).update(
                first_published_at=base_published_at + timezone.timedelta(days=number)
            )
            pages.append(BlogPage.objects.get(pk=page.pk))
        return pages

    def test_blog_page_creation(self):
        page = self.make_blog_page()
        self.assertEqual(page.featured_image.title, "Test image")
        self.assertEqual(page.get_parent().specific, self.index_page)

    def test_dated_blog_page_url_serves_successfully(self):
        page = self.make_blog_page(title="Served page", slug="served-page")

        response = self.client.get(page.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Served page")

    def test_blog_index_map_response_emits_safe_referrer_policy_and_canonical_tile_config(self):
        page = self.make_blog_page(
            title="Mapped post",
            slug="mapped-post",
            manual_latitude=Decimal("64.146600"),
            manual_longitude=Decimal("-21.942600"),
        )

        response = self.client.get(self.index_page.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertNotEqual(response.headers.get("Referrer-Policy"), "no-referrer")
        self.assertContains(response, "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertContains(response, 'referrerPolicy: "strict-origin-when-cross-origin"')
        self.assertNotContains(response, "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertContains(response, page.title)

    def test_resolved_location_prefers_image_geo_metadata(self):
        image = self.make_image(gps_latitude=Decimal("64.100100"), gps_longitude=Decimal("-21.900200"))
        page = self.make_blog_page(
            featured_image=image,
            manual_latitude=Decimal("63.000000"),
            manual_longitude=Decimal("-20.000000"),
        )

        self.assertEqual(page.resolved_latitude, Decimal("64.100100"))
        self.assertEqual(page.resolved_longitude, Decimal("-21.900200"))

    def test_resolved_location_falls_back_to_manual_coordinates(self):
        page = self.make_blog_page(
            manual_latitude=Decimal("65.123456"),
            manual_longitude=Decimal("-19.654321"),
        )

        self.assertEqual(page.resolved_latitude, Decimal("65.123456"))
        self.assertEqual(page.resolved_longitude, Decimal("-19.654321"))
        self.assertTrue(page.has_location)

    def test_coordinates_display_formats_degrees_and_minutes(self):
        page = self.make_blog_page(
            manual_latitude=Decimal("64.146600"),
            manual_longitude=Decimal("-21.942600"),
        )

        self.assertEqual(page.coordinates_display, f"64{chr(176)}09'N x 21{chr(176)}57'W")

    def test_image_metadata_display_uses_featured_image_fields(self):
        image = self.make_image(
            camera_make="FUJIFILM",
            camera_model="X-T4",
            shutter_speed="1/160 sek",
            iso=1600,
            aperture=Decimal("4.50"),
            focal_length_mm=Decimal("23.00"),
        )
        page = self.make_blog_page(featured_image=image)

        self.assertEqual(page.camera_display, "FUJIFILM X-T4")
        self.assertEqual(page.exposure_display, "1/160 sek")
        self.assertEqual(page.iso_display, "1600")
        self.assertEqual(page.aperture_display, "f/4.5")
        self.assertEqual(page.focal_length_display, "23 mm")

    def test_image_metadata_display_returns_empty_strings_for_missing_metadata(self):
        page = self.make_blog_page()

        self.assertEqual(page.camera_display, "")
        self.assertEqual(page.exposure_display, "")
        self.assertEqual(page.iso_display, "")
        self.assertEqual(page.aperture_display, "")
        self.assertEqual(page.focal_length_display, "")

    def test_camera_display_allows_partial_camera_metadata(self):
        image = self.make_image(camera_model="X-T4")
        page = self.make_blog_page(featured_image=image)

        self.assertEqual(page.camera_display, "X-T4")

    def test_blog_page_can_belong_to_multiple_series(self):
        page = self.make_blog_page()
        first_series = self.make_series(title="North", slug="north")
        second_series = self.make_series(title="South", slug="south")

        page.series.add(first_series, second_series)
        page.save_revision().publish()
        page = BlogPage.objects.get(pk=page.pk)

        self.assertEqual(page.series.count(), 2)

    def test_series_page_lists_connected_blog_pages(self):
        page = self.make_blog_page()
        series = self.make_series()
        page.series.add(series)
        page.save_revision().publish()

        self.assertEqual(list(series.connected_posts), [BlogPage.objects.get(pk=page.pk)])

    def test_unsaved_blog_page_can_hold_series_selection(self):
        first_series = self.make_series(title="North", slug="north")
        second_series = self.make_series(title="South", slug="south")
        blog_page = BlogPage(
            title="Draft page",
            slug="draft-page",
            featured_image=self.make_image(),
        )

        blog_page.series = [first_series, second_series]

        self.assertEqual(list(blog_page.series.all()), [first_series, second_series])

    def test_get_context_supports_preview_series_queryset(self):
        first_series = self.make_series(title="North", slug="north")
        second_series = self.make_series(title="South", slug="south")
        blog_page = BlogPage(
            title="Preview page",
            slug="preview-page",
            featured_image=self.make_image(),
        )
        blog_page.series = [first_series, second_series]

        context = blog_page.get_context(self.request_factory.get("/blog/preview/"))

        self.assertEqual(list(context["related_series"]), [first_series, second_series])

    def test_other_blog_posts_returns_three_newer_and_three_older_posts(self):
        pages = self.make_chronological_blog_pages(8)

        other_posts = pages[4].get_other_blog_posts()

        self.assertEqual([post.title for post in other_posts], ["Post 7", "Post 6", "Post 5", "Post 3", "Post 2", "Post 1"])

    def test_other_blog_posts_for_latest_post_returns_previous_six_posts(self):
        pages = self.make_chronological_blog_pages(8)

        other_posts = pages[7].get_other_blog_posts()

        self.assertEqual([post.title for post in other_posts], ["Post 6", "Post 5", "Post 4", "Post 3", "Post 2", "Post 1"])

    def test_other_blog_posts_for_second_latest_post_fills_from_older_posts(self):
        pages = self.make_chronological_blog_pages(8)

        other_posts = pages[6].get_other_blog_posts()

        self.assertEqual([post.title for post in other_posts], ["Post 7", "Post 5", "Post 4", "Post 3", "Post 2", "Post 1"])

    def test_other_blog_posts_for_oldest_post_returns_next_six_posts(self):
        pages = self.make_chronological_blog_pages(8)

        other_posts = pages[0].get_other_blog_posts()

        self.assertEqual([post.title for post in other_posts], ["Post 6", "Post 5", "Post 4", "Post 3", "Post 2", "Post 1"])

    def test_blog_page_context_includes_other_posts(self):
        pages = self.make_chronological_blog_pages(3)

        context = pages[1].get_context(self.request_factory.get("/blog/post-1/"))

        self.assertEqual([post.title for post in context["other_posts"]], ["Post 2", "Post 0"])

    def test_index_includes_pinned_blog_pages_in_overview_list(self):
        pinned_page = self.make_blog_page(title="Pinned", slug="pinned")
        regular_page = self.make_blog_page(title="Regular", slug="regular")
        BlogIndexPagePinnedItem.objects.create(page=self.index_page, target_page=pinned_page)

        context = self.get_index_context()

        self.assertCountEqual(list(context["blog_posts"].object_list), [pinned_page, regular_page])
        self.assertEqual(list(context["pinned_items"]), [self.index_page.pinned_items.first()])

    def test_index_pagination_uses_twenty_items_per_page(self):
        for number in range(25):
            self.make_blog_page(title=f"Post {number}", slug=f"post-{number}", display_date=timezone.now() + timezone.timedelta(minutes=number))

        context = self.get_index_context()

        self.assertEqual(context["blog_posts"].paginator.per_page, 20)
        self.assertEqual(len(context["blog_posts"].object_list), 20)

    def test_filtering_by_year(self):
        self.make_blog_page(title="Old", slug="old", display_date=timezone.make_aware(datetime(2025, 5, 1, 8, 0, 0)))
        matching_page = self.make_blog_page(title="New", slug="new", display_date=timezone.make_aware(datetime(2026, 5, 1, 8, 0, 0)))

        context = self.get_index_context("?year=2026")

        self.assertEqual(list(context["blog_posts"].object_list), [matching_page])

    def test_filtering_by_month(self):
        self.make_blog_page(title="January", slug="january", display_date=timezone.make_aware(datetime(2026, 1, 2, 8, 0, 0)))
        matching_page = self.make_blog_page(title="March", slug="march", display_date=timezone.make_aware(datetime(2026, 3, 2, 8, 0, 0)))

        context = self.get_index_context("?month=3")

        self.assertEqual(list(context["blog_posts"].object_list), [matching_page])

    def test_filtering_by_series(self):
        matching_page = self.make_blog_page(title="In series", slug="in-series")
        other_page = self.make_blog_page(title="Outside series", slug="outside-series")
        series = self.make_series(title="Trips", slug="trips")
        matching_page.series.add(series)
        matching_page.save_revision().publish()

        context = self.get_index_context("?series=trips")

        self.assertEqual(list(context["blog_posts"].object_list), [BlogPage.objects.get(pk=matching_page.pk)])
        self.assertNotIn(other_page, list(context["blog_posts"].object_list))

    def test_pinned_item_validation_requires_exactly_one_target(self):
        page = self.make_blog_page()
        series = self.make_series()

        with self.assertRaises(ValidationError):
            BlogIndexPagePinnedItem(page=self.index_page).clean()

        with self.assertRaises(ValidationError):
            BlogIndexPagePinnedItem(page=self.index_page, target_page=self.index_page).clean()

        item = BlogIndexPagePinnedItem(page=self.index_page, target_page=page)
        item.clean()

        item = BlogIndexPagePinnedItem(page=self.index_page, target_page=series)
        item.clean()

    def test_best_alt_text_fallback_logic(self):
        image = self.make_image(description="Descriptive image text")
        page = self.make_blog_page(title="Fallback title", slug="fallback-title", featured_image=image)
        self.assertEqual(page.best_alt_text, "Descriptive image text")

        page.caption = "Caption wins"
        self.assertEqual(page.best_alt_text, "Caption wins")

    def test_seo_description_fallback_logic(self):
        image = self.make_image(description="Image description fallback")
        page = self.make_blog_page(
            title="SEO post",
            slug="seo-post",
            featured_image=image,
            body=[
                ("rich_text", "<p>Body excerpt for description fallback.</p>"),
            ],
        )

        self.assertEqual(page.seo_description, "Body excerpt for description fallback.")

        page.caption = "Caption summary"
        self.assertEqual(page.seo_description, "Caption summary")

        page.caption = ""
        page.body = []
        self.assertEqual(page.seo_description, "Image description fallback")

    def test_manual_coordinates_must_be_complete_and_in_range(self):
        page = BlogPage(
            title="Invalid",
            slug="invalid",
            featured_image=self.make_image(),
            manual_latitude=Decimal("95.000000"),
        )

        with self.assertRaises(ValidationError):
            page.clean()

    def test_admin_page_renders_manual_geo_map_and_existing_coordinates(self):
        user_model = get_user_model()
        user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(user)
        page = self.make_blog_page(
            title="Mapped admin post",
            slug="mapped-admin-post",
            manual_latitude=Decimal("64.146600"),
            manual_longitude=Decimal("-21.942600"),
        )

        response = self.client.get(reverse("wagtailadmin_pages:edit", args=[page.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "leaflet.js")
        self.assertContains(response, 'data-kyrauga-coordinate-map')
        self.assertContains(response, 'data-latitude="64.146600"')
        self.assertContains(response, 'data-longitude="-21.942600"')
        self.assertContains(response, "data-latitude-input")
        self.assertContains(response, "data-longitude-input")
        self.assertContains(response, 'data-kyrauga-coordinate-search')
        self.assertContains(response, 'data-kyrauga-coordinate-target="search-input"')
        self.assertContains(response, 'type="button"')
        self.assertContains(response, 'data-kyrauga-coordinate-target="search-button"')
        self.assertContains(response, "manual_latitude")
        self.assertContains(response, 'data-kyrauga-coordinate-target="latitude"')


class BlogMapStaticAssetTests(TestCase):
    def test_admin_map_script_uses_canonical_osm_tile_url_and_referrer_policy(self):
        script_path = Path(__file__).resolve().parents[2] / "config" / "static" / "js" / "kyrauga-image-metadata-map.js"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", script)
        self.assertIn("https://nominatim.openstreetmap.org/search", script)
        self.assertIn("fitBounds", script)
        self.assertIn('referrerPolicy: "strict-origin-when-cross-origin"', script)
        self.assertNotIn("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", script)
