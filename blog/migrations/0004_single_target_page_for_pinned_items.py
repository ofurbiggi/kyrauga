from django.db import migrations, models
import django.db.models.deletion


def copy_pinned_targets(apps, schema_editor):
    PinnedItem = apps.get_model("blog", "BlogIndexPagePinnedItem")

    for pinned_item in PinnedItem.objects.all():
        pinned_item.target_page_id = pinned_item.blog_page_id or pinned_item.series_page_id
        pinned_item.save(update_fields=["target_page"])


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0003_alter_blogpage_series"),
    ]

    operations = [
        migrations.AddField(
            model_name="blogindexpagepinneditem",
            name="target_page",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="wagtailcore.page",
            ),
        ),
        migrations.RunPython(copy_pinned_targets, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="blogindexpagepinneditem",
            name="blog_page",
        ),
        migrations.RemoveField(
            model_name="blogindexpagepinneditem",
            name="series_page",
        ),
        migrations.AlterField(
            model_name="blogindexpagepinneditem",
            name="target_page",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="wagtailcore.page",
            ),
        ),
    ]
