import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("repositories", "0005_repository_monitoring_fields")]
    operations = [
        migrations.CreateModel(
            name="RepositoryScoreHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("score_type", models.CharField(choices=[("TREND", "Trend"), ("POTENTIAL", "Potential")], max_length=16)),
                ("algorithm_version", models.CharField(max_length=50)),
                ("score", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("confidence", models.FloatField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ("evidence", models.JSONField(default=dict)),
                ("history_bucket", models.CharField(max_length=13)),
                ("calculated_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_history", to="repositories.repository")),
            ],
            options={"db_table": "repository_score_history"},
        ),
        migrations.AddConstraint(
            model_name="repositoryscorehistory",
            constraint=models.UniqueConstraint(fields=("repository", "score_type", "algorithm_version", "history_bucket"), name="unique_repository_score_history_bucket"),
        ),
        migrations.AddIndex(model_name="repositoryscorehistory", index=models.Index(fields=["repository", "score_type", "-calculated_at"], name="score_history_repo_type_at_idx")),
        migrations.AddIndex(model_name="repositoryscorehistory", index=models.Index(fields=["score_type", "-calculated_at"], name="score_history_type_at_idx")),
    ]
