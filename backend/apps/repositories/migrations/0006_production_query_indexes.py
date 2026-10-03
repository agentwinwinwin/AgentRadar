from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("repositories", "0005_repository_monitoring_fields")]
    operations = [
        migrations.AddIndex(
            model_name="repository",
            index=models.Index(fields=["category", "is_disabled", "is_fork", "-stars"], name="repo_cat_stars_idx"),
        ),
        migrations.AddIndex(
            model_name="repository",
            index=models.Index(fields=["monitoring_enabled", "next_snapshot_at"], name="repo_snapshot_due_idx"),
        ),
    ]
