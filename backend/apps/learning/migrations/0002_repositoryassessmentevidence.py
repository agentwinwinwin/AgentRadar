from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("learning", "0001_initial"), ("repositories", "0008_repositorylocalization")]
    operations = [
        migrations.CreateModel(
            name="RepositoryAssessmentEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("NOT_CHECKED", "Not checked"), ("PARTIAL", "Partial"), ("COMPLETE", "Complete"), ("FAILED", "Failed")], default="NOT_CHECKED", max_length=20)),
                ("readme", models.BooleanField(blank=True, null=True)),
                ("docs", models.BooleanField(blank=True, null=True)),
                ("getting_started", models.BooleanField(blank=True, null=True)),
                ("examples", models.BooleanField(blank=True, null=True)),
                ("architecture", models.BooleanField(blank=True, null=True)),
                ("contributing", models.BooleanField(blank=True, null=True)),
                ("security", models.BooleanField(blank=True, null=True)),
                ("testing", models.BooleanField(blank=True, null=True)),
                ("deployment", models.BooleanField(blank=True, null=True)),
                ("container", models.BooleanField(blank=True, null=True)),
                ("matched_paths", models.JSONField(default=list)),
                ("source", models.CharField(default="GITHUB_CONTENTS_WHITELIST", max_length=40)),
                ("request_count", models.PositiveSmallIntegerField(default=0)),
                ("checked_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("repository", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="assessment_evidence", to="repositories.repository")),
            ],
            options={"db_table": "repository_assessment_evidence"},
        )
    ]
