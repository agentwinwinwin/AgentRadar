import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("auth", "0012_alter_user_first_name_max_length")]

    operations = [
        migrations.CreateModel(
            name="CopilotConversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="copilot_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "copilot_conversations", "ordering": ("-updated_at", "-id")},
        ),
        migrations.CreateModel(
            name="CopilotMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("USER", "User"), ("ASSISTANT", "Assistant")], max_length=16)),
                ("content", models.TextField()),
                ("response", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="agent.copilotconversation")),
            ],
            options={"db_table": "copilot_messages", "ordering": ("id",)},
        ),
        migrations.AddConstraint(
            model_name="copilotconversation",
            constraint=models.UniqueConstraint(fields=("owner", "session_id"), name="unique_copilot_owner_session"),
        ),
        migrations.AddIndex(
            model_name="copilotmessage",
            index=models.Index(fields=["conversation", "id"], name="copilot_message_order_idx"),
        ),
    ]
