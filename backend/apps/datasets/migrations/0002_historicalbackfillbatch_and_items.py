import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("datasets", "0001_initial"), ("repositories", "0004_alter_repository_forks_alter_repository_open_issues_and_more")]
    operations = [
        migrations.CreateModel(
            name="HistoricalBackfillBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("RUNNING", "Running"), ("COMPLETED", "Completed"), ("PARTIAL", "Partial")], default="PENDING", max_length=20)),
                ("configuration", models.JSONField(default=dict)),
                ("endpoint_request_counts", models.JSONField(default=dict)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "historical_backfill_batches"},
        ),
        migrations.CreateModel(
            name="HistoricalBackfillBatchItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sample_date", models.DateField()),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("RUNNING", "Running"), ("SUCCEEDED", "Succeeded"), ("FAILED", "Failed")], default="PENDING", max_length=20)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("windows_created", models.PositiveSmallIntegerField(default=0)),
                ("endpoint_request_counts", models.JSONField(default=dict)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="datasets.historicalbackfillbatch")),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historical_backfill_items", to="repositories.repository")),
            ],
            options={"db_table": "historical_backfill_batch_items"},
        ),
        migrations.AddConstraint(
            model_name="historicalbackfillbatchitem",
            constraint=models.UniqueConstraint(fields=("batch", "repository", "sample_date"), name="unique_backfill_batch_repository_sample"),
        ),
    ]
