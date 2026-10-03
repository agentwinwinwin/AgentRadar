from django.conf import settings


def test_forecast_tasks_use_ml_queue() -> None:
    assert settings.CELERY_TASK_ROUTES["forecasts.*"]["queue"] == "ml"
