from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def bind_legacy_data(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    user, _ = User.objects.get_or_create(username="legacy-local", defaults={"password": "!"})
    Watchlist = apps.get_model("watchlists", "Watchlist")
    WatchlistEvent = apps.get_model("watchlists", "WatchlistEvent")
    ScheduledReport = apps.get_model("watchlists", "ScheduledReport")
    Alert = apps.get_model("watchlists", "Alert")
    AlertReceipt = apps.get_model("watchlists", "AlertReceipt")
    Watchlist.objects.filter(owner__isnull=True).update(owner=user)
    WatchlistEvent.objects.filter(owner__isnull=True).update(owner=user)
    ScheduledReport.objects.filter(owner__isnull=True).update(owner=user)
    AlertReceipt.objects.bulk_create(
        [
            AlertReceipt(owner=user, alert=alert, status=alert.status)
            for alert in Alert.objects.all()
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("watchlists", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="watchlist",
            name="owner",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name="watchlistevent",
            name="owner",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name="scheduledreport",
            name="owner",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.CreateModel(
            name="AlertReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("UNREAD", "Unread"), ("READ", "Read"), ("DISMISSED", "Dismissed")], db_index=True, default="UNREAD", max_length=12)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("alert", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="receipts", to="watchlists.alert")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "alert_receipts"},
        ),
        migrations.AddConstraint(
            model_name="alertreceipt",
            constraint=models.UniqueConstraint(fields=("owner", "alert"), name="unique_owner_alert_receipt"),
        ),
        migrations.RunPython(bind_legacy_data, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="watchlist", name="unique_owner_watchlist"),
        migrations.RemoveConstraint(model_name="scheduledreport", name="unique_scheduled_report_period"),
        migrations.RemoveField(model_name="watchlist", name="owner_key"),
        migrations.RemoveField(model_name="watchlistevent", name="owner_key"),
        migrations.RemoveField(model_name="scheduledreport", name="owner_key"),
        migrations.RemoveField(model_name="alert", name="status"),
        migrations.AlterField(model_name="watchlist", name="owner", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(model_name="watchlistevent", name="owner", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(model_name="scheduledreport", name="owner", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        migrations.AddConstraint(model_name="watchlist", constraint=models.UniqueConstraint(fields=("owner", "name"), name="unique_owner_watchlist")),
        migrations.AddConstraint(model_name="scheduledreport", constraint=models.UniqueConstraint(fields=("owner", "report_type", "period_start", "period_end", "rule_version"), name="unique_scheduled_report_period")),
    ]
