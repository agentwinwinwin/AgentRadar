import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("activities", "0001_initial"),
        ("snapshots", "0001_initial"),
        ("trends", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricalActivityWindow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("window_start", models.DateField()),
                ("window_end", models.DateField()),
                ("data_origin", models.CharField(choices=[("BACKFILLED", "Backfilled from historical API"), ("OBSERVED", "Observed by AgentRadar")], max_length=20)),
                ("commits", models.PositiveIntegerField(blank=True, null=True)),
                ("prs_created", models.PositiveIntegerField(blank=True, null=True)),
                ("prs_merged", models.PositiveIntegerField(blank=True, null=True)),
                ("issues_created", models.PositiveIntegerField(blank=True, null=True)),
                ("issues_closed", models.PositiveIntegerField(blank=True, null=True)),
                ("active_contributors", models.PositiveIntegerField(blank=True, null=True)),
                ("releases", models.PositiveIntegerField(blank=True, null=True)),
                ("days_since_last_release", models.PositiveIntegerField(blank=True, null=True)),
                ("data_completeness", models.FloatField(validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ("source_metadata", models.JSONField(default=dict)),
                ("collected_at", models.DateTimeField(auto_now=True)),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historical_activity_windows", to="repositories.repository")),
            ],
            options={"db_table": "historical_activity_windows"},
        ),
        migrations.CreateModel(
            name="TrainingSample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sample_at", models.DateTimeField(db_index=True)),
                ("feature_window_start", models.DateField()),
                ("feature_window_end", models.DateField()),
                ("label_window_start", models.DateField()),
                ("label_window_end", models.DateField()),
                ("category", models.CharField(choices=[("AGENT_FRAMEWORK", "Agent framework"), ("CODING_AGENT", "Coding agent"), ("BROWSER_AGENT", "Browser agent"), ("RESEARCH_AGENT", "Research agent"), ("MULTI_AGENT", "Multi-agent"), ("AGENT_MEMORY", "Agent memory"), ("AGENT_WORKFLOW", "Agent workflow"), ("MCP_TOOL", "MCP tool"), ("COMPUTER_USE", "Computer use"), ("AGENT_OBSERVABILITY", "Agent observability"), ("AGENT_SECURITY", "Agent security"), ("OTHER_AGENT", "Other agent")], max_length=50)),
                ("age_cohort", models.CharField(max_length=30)),
                ("features", models.JSONField(default=dict)),
                ("label", models.PositiveSmallIntegerField()),
                ("label_score", models.FloatField(validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(100.0)])),
                ("feature_version", models.CharField(max_length=50)),
                ("label_version", models.CharField(max_length=50)),
                ("data_origin", models.CharField(choices=[("BACKFILLED", "Backfilled from historical API"), ("OBSERVED", "Observed by AgentRadar")], max_length=20)),
                ("label_evidence", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="training_samples", to="repositories.repository")),
            ],
            options={"db_table": "training_samples"},
        ),
        migrations.AddConstraint(model_name="historicalactivitywindow", constraint=models.UniqueConstraint(fields=("repository", "window_start", "window_end", "data_origin"), name="unique_repository_historical_activity_window")),
        migrations.AddConstraint(model_name="historicalactivitywindow", constraint=models.CheckConstraint(condition=models.Q(("window_start__lte", models.F("window_end"))), name="historical_window_start_not_after_end")),
        migrations.AddConstraint(model_name="historicalactivitywindow", constraint=models.CheckConstraint(condition=models.Q(("data_completeness__gte", 0.0), ("data_completeness__lte", 1.0)), name="historical_window_completeness_between_zero_and_one")),
        migrations.AddConstraint(model_name="trainingsample", constraint=models.UniqueConstraint(fields=("repository", "sample_at", "feature_version", "label_version"), name="unique_repository_training_sample_version")),
        migrations.AddConstraint(model_name="trainingsample", constraint=models.CheckConstraint(condition=models.Q(("label__in", (0, 1))), name="training_sample_binary_label")),
        migrations.AddConstraint(model_name="trainingsample", constraint=models.CheckConstraint(condition=models.Q(("label_score__gte", 0.0), ("label_score__lte", 100.0)), name="training_sample_label_score_between_zero_and_hundred")),
    ]
