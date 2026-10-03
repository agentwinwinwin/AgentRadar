import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("repositories", "0004_alter_repository_forks_alter_repository_open_issues_and_more")
    ]
    operations = [
        migrations.CreateModel(
            name="MLModel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("model_name", models.CharField(max_length=100)),
                ("model_version", models.CharField(max_length=100, unique=True)),
                ("feature_version", models.CharField(max_length=50)),
                ("label_version", models.CharField(max_length=50)),
                ("algorithm", models.CharField(max_length=50)),
                ("training_start", models.DateTimeField()),
                ("training_end", models.DateTimeField()),
                ("validation_metrics", models.JSONField(default=dict)),
                ("test_metrics", models.JSONField(default=dict)),
                ("dataset_quality", models.JSONField(default=dict)),
                ("feature_importance", models.JSONField(default=dict)),
                ("artifact_path", models.CharField(max_length=1000)),
                ("artifact_sha256", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("TRAINED", "Trained"),
                            ("VALIDATED", "Validated"),
                            ("ACTIVE", "Active"),
                            ("RETIRED", "Retired"),
                        ],
                        default="TRAINED",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "ml_models"},
        ),
        migrations.CreateModel(
            name="RepositoryForecast",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("model_version", models.CharField(max_length=100)),
                ("sample_at", models.DateTimeField()),
                ("forecast_horizon_days", models.PositiveSmallIntegerField(default=30)),
                (
                    "high_growth_probability",
                    models.FloatField(
                        validators=[
                            django.core.validators.MinValueValidator(0.0),
                            django.core.validators.MaxValueValidator(1.0),
                        ]
                    ),
                ),
                ("prediction", models.PositiveSmallIntegerField()),
                (
                    "confidence",
                    models.FloatField(
                        validators=[
                            django.core.validators.MinValueValidator(0.0),
                            django.core.validators.MaxValueValidator(1.0),
                        ]
                    ),
                ),
                ("feature_snapshot", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="forecasts",
                        to="forecasts.mlmodel",
                    ),
                ),
                (
                    "repository",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="forecasts",
                        to="repositories.repository",
                    ),
                ),
            ],
            options={"db_table": "repository_forecasts"},
        ),
        migrations.AddConstraint(
            model_name="mlmodel",
            constraint=models.UniqueConstraint(
                fields=("model_name", "model_version"), name="unique_ml_model_version"
            ),
        ),
        migrations.AddConstraint(
            model_name="repositoryforecast",
            constraint=models.UniqueConstraint(
                fields=("repository", "model_version", "sample_at"),
                name="unique_repository_forecast_model_sample",
            ),
        ),
        migrations.AddConstraint(
            model_name="repositoryforecast",
            constraint=models.CheckConstraint(
                condition=models.Q(("prediction__in", (0, 1))), name="forecast_binary_prediction"
            ),
        ),
    ]
