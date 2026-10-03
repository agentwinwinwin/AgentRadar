from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("watchlists", "0002_user_isolation")]
    operations = [
        migrations.AddIndex(model_name="alert", index=models.Index(fields=["repository", "-detected_at"], name="alert_repo_detected_idx")),
        migrations.AddIndex(model_name="alertreceipt", index=models.Index(fields=["owner", "status"], name="receipt_owner_status_idx")),
        migrations.AddIndex(model_name="scheduledreport", index=models.Index(fields=["owner", "report_type", "-period_end"], name="report_owner_type_period_idx")),
    ]
