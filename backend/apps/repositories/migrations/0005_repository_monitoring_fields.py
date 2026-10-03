from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("repositories", "0004_alter_repository_forks_alter_repository_open_issues_and_more")]

    operations = [
        migrations.AddField(
            model_name="repository",
            name="monitoring_tier",
            field=models.CharField(
                choices=[
                    ("NEW", "New"), ("HOT", "Hot"), ("RISING", "Rising"),
                    ("NORMAL", "Normal"), ("STABLE", "Stable"),
                    ("DORMANT", "Dormant"), ("ARCHIVED", "Archived"),
                ],
                db_index=True, default="NORMAL", max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="repository", name="monitoring_enabled",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="repository", name="last_snapshot_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="repository", name="next_snapshot_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
