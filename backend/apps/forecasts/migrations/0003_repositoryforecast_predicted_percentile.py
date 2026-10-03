import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("forecasts", "0002_modeltrainingrun")]

    operations = [
        migrations.AddField(
            model_name="repositoryforecast",
            name="percentile_model_version",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="repositoryforecast",
            name="predicted_activity_percentile",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(100.0),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="repositoryforecast",
            constraint=models.CheckConstraint(
                condition=models.Q(predicted_activity_percentile__isnull=True)
                | (
                    models.Q(predicted_activity_percentile__gte=0.0)
                    & models.Q(predicted_activity_percentile__lte=100.0)
                ),
                name="forecast_percentile_between_zero_and_hundred",
            ),
        ),
    ]
