import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("trends", "0001_initial"),
        ("repositories", "0004_alter_repository_forks_alter_repository_open_issues_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="RepositoryPotentialScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("potential_score", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("confidence", models.FloatField(validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ("algorithm_version", models.CharField(max_length=50)),
                ("evidence", models.JSONField(default=dict)),
                ("calculated_at", models.DateTimeField()),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="potential_scores", to="repositories.repository")),
            ],
            options={"db_table": "repository_potential_scores"},
        ),
        migrations.AddConstraint(
            model_name="repositorypotentialscore",
            constraint=models.UniqueConstraint(fields=("repository", "algorithm_version"), name="unique_repository_potential_algorithm"),
        ),
        migrations.AddConstraint(
            model_name="repositorypotentialscore",
            constraint=models.CheckConstraint(condition=models.Q(("confidence__gte", 0.0), ("confidence__lte", 1.0)), name="potential_confidence_between_zero_and_one"),
        ),
    ]
