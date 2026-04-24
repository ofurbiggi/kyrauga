from decimal import Decimal
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import strip_tags
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from taggit.models import TaggedItemBase
from wagtail import blocks
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.blocks import RichTextBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images import get_image_model_string
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Orderable, Page
from wagtail.search import index
from wagtail.url_routing import RouteResult


def format_decimal(value):
    if value in (None, ""):
        return ""
    normalized = Decimal(value).normalize()
    return format(normalized, "f").rstrip("0").rstrip(".") or "0"


class QuoteBlock(blocks.StructBlock):
    quote = blocks.TextBlock(required=True)
    attribution = blocks.CharBlock(required=False)

    class Meta:
        icon = "openquote"
        label = "Quote"
        template = "blog/blocks/quote_block.html"


class GalleryBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False)
    images = blocks.ListBlock(ImageChooserBlock(), min_num=1)
    caption = blocks.TextBlock(required=False)

    class Meta:
        icon = "image"
        label = "Gallery"
        template = "blog/blocks/gallery_block.html"


class BlogBodyBlock(blocks.StreamBlock):
    rich_text = RichTextBlock(required=False)
    image = ImageChooserBlock(required=False)
    gallery = GalleryBlock(required=False)
    quote = QuoteBlock(required=False)


class BlogPageTag(TaggedItemBase):
    content_object = ParentalKey(
        "blog.BlogPage",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


class BlogIndexPage(Page):
    intro = RichTextField(blank=True)

    parent_page_types = ["home.HomePage"]
    subpage_types = ["blog.BlogPage", "blog.PhotoSeriesPage"]
    template = "blog/blog_index_page.html"

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        InlinePanel("pinned_items", label="Pinned editorial items"),
    ]

    def get_pinned_items(self):
        return self.pinned_items.select_related("blog_page", "series_page").all()

    def get_pinned_blog_page_ids(self):
        return list(
            self.pinned_items.exclude(blog_page__isnull=True).values_list("blog_page_id", flat=True)
        )

    def get_base_blog_pages_queryset(self):
        return (
            BlogPage.objects.child_of(self)
            .live()
            .public()
            .select_related("featured_image")
            .prefetch_related("series")
            .order_by("-display_date", "-first_published_at")
        )

    def get_available_filters(self, queryset):
        datetimes = [value for value in queryset.values_list("display_date", flat=True) if value]
        years = sorted({value.year for value in datetimes}, reverse=True)
        year_param = self._parse_int(self.get_filter_state().get("year"))
        months_source = [value for value in datetimes if year_param is None or value.year == year_param]
        months = sorted({value.month for value in months_source}, reverse=True)
        series = (
            PhotoSeriesPage.objects.child_of(self)
            .live()
            .public()
            .order_by("title")
        )
        return {
            "years": years,
            "months": months,
            "series": series,
        }

    def _parse_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def get_filter_state(self):
        request = getattr(self, "_context_request", None)
        if request is None:
            return {"year": "", "month": "", "series": ""}
        return {
            "year": request.GET.get("year", "").strip(),
            "month": request.GET.get("month", "").strip(),
            "series": request.GET.get("series", "").strip(),
        }

    def get_filtered_blog_pages(self):
        queryset = self.get_base_blog_pages_queryset().exclude(pk__in=self.get_pinned_blog_page_ids())
        filters = self.get_filter_state()

        year = self._parse_int(filters["year"])
        month = self._parse_int(filters["month"])
        series = filters["series"]

        if year:
            queryset = queryset.filter(display_date__year=year)
        if month:
            queryset = queryset.filter(display_date__month=month)
        if series:
            series_filter = Q(series__slug=series)
            series_id = self._parse_int(series)
            if series_id:
                series_filter |= Q(series__id=series_id)
            queryset = queryset.filter(series_filter).distinct()

        return queryset

    def get_map_points(self):
        points = []
        for blog_page in self.get_base_blog_pages_queryset():
            if not blog_page.has_location:
                continue
            thumbnail_url = ""
            try:
                thumbnail_url = blog_page.featured_image.get_rendition("fill-200x150").url
            except Exception:
                thumbnail_url = ""
            points.append(
                {
                    "title": blog_page.title,
                    "url": blog_page.url,
                    "latitude": float(blog_page.resolved_latitude),
                    "longitude": float(blog_page.resolved_longitude),
                    "thumbnail": thumbnail_url,
                }
            )
        return points

    def route(self, request, path_components):
        if len(path_components) == 3:
            year, month, slug = path_components
            if year.isdigit() and month.isdigit():
                blog_page = BlogPage.objects.child_of(self).live().filter(
                    slug=slug,
                    display_date__year=int(year),
                    display_date__month=int(month),
                ).first()
                if blog_page:
                    return RouteResult(blog_page.specific)
        if len(path_components) == 2 and path_components[0] == "series":
            series_page = PhotoSeriesPage.objects.child_of(self).live().filter(slug=path_components[1]).first()
            if series_page:
                return RouteResult(series_page.specific)
        return super().route(request, path_components)

    def get_context(self, request, *args, **kwargs):
        self._context_request = request
        context = super().get_context(request, *args, **kwargs)
        pinned_items = self.get_pinned_items()
        filtered_queryset = self.get_filtered_blog_pages()
        paginator = Paginator(filtered_queryset, 20)
        page_number = request.GET.get("page")
        paginated_posts = paginator.get_page(page_number)
        map_points = self.get_map_points()

        context.update(
            {
                "pinned_items": pinned_items,
                "blog_posts": paginated_posts,
                "map_points": map_points,
                "available_filters": self.get_available_filters(self.get_base_blog_pages_queryset().exclude(pk__in=self.get_pinned_blog_page_ids())),
                "active_filters": self.get_filter_state(),
            }
        )
        return context


class PhotoSeriesPage(Page):
    intro = RichTextField(blank=True)
    cover_image = models.ForeignKey(
        get_image_model_string(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    body = StreamField(BlogBodyBlock(), blank=True, use_json_field=True)

    parent_page_types = ["blog.BlogIndexPage"]
    subpage_types = []
    template = "blog/photo_series_page.html"

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("cover_image"),
        FieldPanel("body"),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("title"),
        index.SearchField("intro"),
    ]

    @property
    def connected_posts(self):
        return (
            BlogPage.objects.live()
            .public()
            .filter(series=self)
            .select_related("featured_image")
            .order_by("-display_date", "-first_published_at")
        )

    @property
    def connected_posts_count(self):
        return self.connected_posts.count()

    def get_url_parts(self, request=None):
        url_parts = super().get_url_parts(request=request)
        if not url_parts:
            return None
        parent_parts = self.get_parent().specific.get_url_parts(request=request)
        if not parent_parts:
            return url_parts
        site_id, root_url, _page_path = url_parts
        parent_path = parent_parts[2]
        return site_id, root_url, f"{parent_path}series/{self.slug}/"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["posts"] = self.connected_posts
        return context


class BlogPage(Page):
    featured_image = models.ForeignKey(
        get_image_model_string(),
        on_delete=models.PROTECT,
        related_name="+",
    )
    caption = models.TextField(blank=True)
    body = StreamField(BlogBodyBlock(), blank=True, use_json_field=True)
    display_date = models.DateTimeField(default=timezone.now)
    tags = ClusterTaggableManager(through=BlogPageTag, blank=True)
    series = ParentalManyToManyField("blog.PhotoSeriesPage", blank=True, related_name="blog_pages")
    manual_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    manual_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    parent_page_types = ["blog.BlogIndexPage"]
    subpage_types = []
    template = "blog/blog_page.html"

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("featured_image"),
                FieldPanel("caption"),
                FieldPanel("body"),
            ],
            heading="Main content",
        ),
        MultiFieldPanel(
            [
                FieldPanel("display_date"),
            ],
            heading="Publishing",
        ),
        MultiFieldPanel(
            [
                FieldPanel("series"),
                FieldPanel("tags"),
            ],
            heading="Relationships",
        ),
        MultiFieldPanel(
            [
                FieldPanel("manual_latitude"),
                FieldPanel("manual_longitude"),
            ],
            heading="Manual geo fallback",
        ),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("title"),
        index.SearchField("caption"),
    ]

    def clean(self):
        super().clean()
        latitude_present = self.manual_latitude is not None
        longitude_present = self.manual_longitude is not None
        if latitude_present != longitude_present:
            raise ValidationError("Manual latitude and longitude must either both be set or both be empty.")
        if self.manual_latitude is not None and not (-90 <= self.manual_latitude <= 90):
            raise ValidationError("Latitude must be between -90 and 90.")
        if self.manual_longitude is not None and not (-180 <= self.manual_longitude <= 180):
            raise ValidationError("Longitude must be between -180 and 180.")

    @property
    def resolved_latitude(self):
        if self.featured_image and self.featured_image.gps_latitude is not None:
            return self.featured_image.gps_latitude
        return self.manual_latitude

    @property
    def resolved_longitude(self):
        if self.featured_image and self.featured_image.gps_longitude is not None:
            return self.featured_image.gps_longitude
        return self.manual_longitude

    @property
    def has_location(self):
        return self.resolved_latitude is not None and self.resolved_longitude is not None

    @property
    def aperture_display(self):
        if not self.featured_image or self.featured_image.aperture is None:
            return ""
        return f"f/{format_decimal(self.featured_image.aperture)}"

    @property
    def focal_length_display(self):
        if not self.featured_image or self.featured_image.focal_length_mm is None:
            return ""
        return f"{format_decimal(self.featured_image.focal_length_mm)} mm"

    @property
    def exposure_display(self):
        if not self.featured_image:
            return ""
        return self.featured_image.shutter_speed

    @property
    def best_alt_text(self):
        if self.featured_image:
            image_field_names = {field.name for field in self.featured_image._meta.get_fields()}
            if "alt_text" in image_field_names and self.featured_image.alt_text:
                return self.featured_image.alt_text
        if self.caption:
            return self.caption
        if self.featured_image and self.featured_image.description:
            return self.featured_image.description
        return self.title

    def body_excerpt(self):
        fragments = []
        for block in self.body:
            if block.block_type == "rich_text":
                fragments.append(strip_tags(str(block.value)))
            elif block.block_type == "quote":
                fragments.append(block.value.get("quote", ""))
                fragments.append(block.value.get("attribution", ""))
            elif block.block_type == "gallery":
                fragments.append(block.value.get("caption", ""))
        excerpt = " ".join(fragment.strip() for fragment in fragments if fragment).strip()
        return excerpt[:160]

    @property
    def seo_description(self):
        if self.caption:
            return self.caption
        excerpt = self.body_excerpt()
        if excerpt:
            return excerpt
        if self.featured_image and self.featured_image.description:
            return self.featured_image.description
        return ""

    def map_embed_url(self):
        if not self.has_location:
            return ""
        latitude = float(self.resolved_latitude)
        longitude = float(self.resolved_longitude)
        lat_delta = 0.01
        lon_delta = 0.02
        params = urlencode(
            {
                "bbox": f"{longitude - lon_delta},{latitude - lat_delta},{longitude + lon_delta},{latitude + lat_delta}",
                "layer": "mapnik",
                "marker": f"{latitude},{longitude}",
            }
        )
        return f"https://www.openstreetmap.org/export/embed.html?{params}"

    def map_link_url(self):
        if not self.has_location:
            return ""
        latitude = float(self.resolved_latitude)
        longitude = float(self.resolved_longitude)
        return f"https://www.openstreetmap.org/?{urlencode({'mlat': latitude, 'mlon': longitude, 'zoom': 14})}"

    def get_url_parts(self, request=None):
        url_parts = super().get_url_parts(request=request)
        if not url_parts:
            return None
        parent_parts = self.get_parent().specific.get_url_parts(request=request)
        if not parent_parts:
            return url_parts
        site_id, root_url, _page_path = url_parts
        parent_path = parent_parts[2]
        local_display_date = timezone.localtime(self.display_date) if timezone.is_aware(self.display_date) else self.display_date
        return site_id, root_url, f"{parent_path}{local_display_date:%Y}/{local_display_date:%m}/{self.slug}/"

    def get_related_series_for_display(self):
        related_series = self.series.all()
        if hasattr(related_series, "live"):
            related_series = related_series.live()
        if hasattr(related_series, "public"):
            related_series = related_series.public()
        return related_series

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        og_image_url = ""
        try:
            og_image_url = self.featured_image.get_rendition("fill-1200x630").url
        except Exception:
            og_image_url = ""
        context.update(
            {
                "related_series": self.get_related_series_for_display(),
                "og_image_url": og_image_url,
            }
        )
        return context


class BlogIndexPagePinnedItem(Orderable):
    page = ParentalKey(
        "blog.BlogIndexPage",
        related_name="pinned_items",
        on_delete=models.CASCADE,
    )
    blog_page = models.ForeignKey(
        "blog.BlogPage",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    series_page = models.ForeignKey(
        "blog.PhotoSeriesPage",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    panels = [
        FieldPanel("blog_page"),
        FieldPanel("series_page"),
    ]

    def clean(self):
        super().clean()
        if bool(self.blog_page) == bool(self.series_page):
            raise ValidationError("Choose exactly one pinned target: either a blog page or a series page.")

    @property
    def pinned_object(self):
        return self.blog_page or self.series_page

    @property
    def is_blog_page(self):
        return self.blog_page_id is not None

    @property
    def is_series_page(self):
        return self.series_page_id is not None
