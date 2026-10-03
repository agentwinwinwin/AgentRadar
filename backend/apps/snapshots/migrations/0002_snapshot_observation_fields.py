from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("snapshots", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="repositorysnapshot", name="github_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="repositorysnapshot", name="is_archived",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="repositorysnapshot", name="data_origin",
            field=models.CharField(default="OBSERVED", max_length=20),
        ),
        migrations.AddField(
            model_name="repositorysnapshot", name="watchers",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
    ]
