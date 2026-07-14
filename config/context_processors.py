from django.conf import settings


def analytics(request):
    return {
        "ga_measurement_id": getattr(settings, "GA_MEASUREMENT_ID", ""),
    }
