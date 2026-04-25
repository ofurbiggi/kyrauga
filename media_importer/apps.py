from django.apps import AppConfig


class MediaImporterConfig(AppConfig):
    name = 'media_importer'

    def ready(self):
        from . import signals  # noqa: F401
