from django.conf import settings
from django.db import models


class CopilotConversation(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="copilot_conversations",
    )
    session_id = models.CharField(max_length=64)
    title = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "copilot_conversations"
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "session_id"),
                name="unique_copilot_owner_session",
            )
        ]
        ordering = ("-updated_at", "-id")

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.title}"


class CopilotMessage(models.Model):
    class Role(models.TextChoices):
        USER = "USER", "User"
        ASSISTANT = "ASSISTANT", "Assistant"

    conversation = models.ForeignKey(
        CopilotConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "copilot_messages"
        ordering = ("id",)
        indexes = [models.Index(fields=("conversation", "id"), name="copilot_message_order_idx")]

    def __str__(self) -> str:
        return f"{self.conversation_id}:{self.role}:{self.id}"
