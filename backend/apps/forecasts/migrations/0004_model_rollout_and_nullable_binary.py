import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("forecasts", "0003_repositoryforecast_predicted_percentile")]

    operations = [
        migrations.AddField(
            model_name="mlmodel",
            name="activated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mlmodel",
            name="prediction_rollout",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="mlmodel",
            name="prediction_rollout_status",
            field=models.CharField(
                choices=[
                    ("NOT_STARTED", "Not started"), ("QUEUED", "Queued"),
                    ("RUNNING", "Running"), ("COMPLETED", "Completed"),
                    ("PARTIAL", "Partial"), ("FAILED", "Failed"),
                ],
                default="NOT_STARTED",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="mlmodel",
            name="retraining_targets",
            field=models.JSONField(default=dict),
        ),
        migrations.RemoveConstraint(
            model_name="repositoryforecast", name="forecast_binary_prediction"
        ),
        migrations.AlterField(
            model_name="repositoryforecast",
            name="high_growth_probability",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="repositoryforecast",
            name="prediction",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="repositoryforecast",
            constraint=models.CheckConstraint(
                condition=models.Q(prediction__isnull=True) | models.Q(prediction__in=(0, 1)),
                name="forecast_binary_prediction",
            ),
        ),
    ]
