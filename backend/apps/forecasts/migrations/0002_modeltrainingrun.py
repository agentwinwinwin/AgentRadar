import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("forecasts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelTrainingRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("singleton_key", models.CharField(default="forecast-v1-training", editable=False, max_length=50)),
                ("status", models.CharField(choices=[("QUEUED", "Queued"), ("RUNNING", "Running"), ("COMPLETED", "Completed"), ("FAILED", "Failed"), ("BLOCKED", "Blocked")], default="QUEUED", max_length=20)),
                ("feature_version", models.CharField(max_length=50)),
                ("label_version", models.CharField(max_length=50)),
                ("celery_task_id", models.CharField(max_length=255, unique=True)),
                ("dataset_gate_snapshot", models.JSONField(default=dict)),
                ("split_readiness_snapshot", models.JSONField(default=dict)),
                ("result", models.JSONField(default=dict)),
                ("error_code", models.CharField(blank=True, max_length=80)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="model_training_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "model_training_runs", "ordering": ("-requested_at",)},
        ),
        migrations.AddIndex(model_name="modeltrainingrun", index=models.Index(fields=["status", "-requested_at"], name="model_train_status_8ad219_idx")),
        migrations.AddConstraint(model_name="modeltrainingrun", constraint=models.UniqueConstraint(condition=models.Q(("status__in", ("QUEUED", "RUNNING"))), fields=("singleton_key",), name="unique_inflight_forecast_training")),
    ]
