from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("datasets", "0007_acquisitionqueryshard_execution_count_and_more")]

    operations = [
        migrations.AddField(
            model_name="trainingsample",
            name="future_activity_percentile",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(100.0),
                ],
            ),
        ),
        migrations.AddField(
            model_name="trainingsample",
            name="binary_top20_label",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trainingsample",
            name="label_cohort_size",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="trainingsample",
            constraint=models.CheckConstraint(
                condition=models.Q(future_activity_percentile__isnull=True)
                | (
                    models.Q(future_activity_percentile__gte=0.0)
                    & models.Q(future_activity_percentile__lte=100.0)
                ),
                name="training_future_percentile_between_zero_and_hundred",
            ),
        ),
        migrations.AddConstraint(
            model_name="trainingsample",
            constraint=models.CheckConstraint(
                condition=models.Q(binary_top20_label__isnull=True)
                | models.Q(binary_top20_label__in=(0, 1)),
                name="training_binary_top20_label_valid",
            ),
        ),
    ]
