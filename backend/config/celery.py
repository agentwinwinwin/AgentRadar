import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("agentradar")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Register structured lifecycle logs after Celery has initialised.
from apps.common import celery_observability  # noqa: E402, F401
