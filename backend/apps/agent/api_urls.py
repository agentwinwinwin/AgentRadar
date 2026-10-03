from django.urls import path

from .api_views import (
    CopilotChatStreamView,
    CopilotChatView,
    CopilotConversationDetailView,
    CopilotConversationListView,
)

urlpatterns = [
    path("copilot/chat", CopilotChatView.as_view(), name="copilot-chat"),
    path("copilot/chat/stream", CopilotChatStreamView.as_view(), name="copilot-chat-stream"),
    path("copilot/history", CopilotConversationListView.as_view(), name="copilot-history"),
    path(
        "copilot/history/<int:conversation_id>",
        CopilotConversationDetailView.as_view(),
        name="copilot-history-detail",
    ),
]
