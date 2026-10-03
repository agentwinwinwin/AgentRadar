from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.agent.models import CopilotConversation, CopilotMessage


@pytest.mark.django_db
def test_copilot_api_validates_input_and_returns_runtime_result():
    client = APIClient()
    user = get_user_model().objects.create_user(username="agent-user", password="test-password")
    client.force_authenticate(user)
    assert client.post(reverse("copilot-chat"), {"message": ""}, format="json").status_code == 400
    payload = {"answer": "有证据的回答", "session_id": "session-abcdefghijklmnop"}
    with patch("apps.agent.api_views.PMCopilotRuntime") as runtime:
        runtime.return_value.chat.return_value = payload
        response = client.post(reverse("copilot-chat"), {"message": "分析项目"}, format="json")
    assert response.status_code == 200
    assert response.json() == payload
    runtime.assert_called_once_with(actor_user_id=user.id)


@pytest.mark.django_db
def test_copilot_stream_emits_status_validated_deltas_and_complete_result():
    client = APIClient()
    user = get_user_model().objects.create_user(username="stream-user", password="test-password")
    client.force_authenticate(user)
    payload = {
        "answer": "这是经过证据校验的回答。",
        "session_id": "session-abcdefghijklmnop",
        "warnings": [],
        "evidence": [],
    }
    with patch("apps.agent.api_views.PMCopilotRuntime") as runtime:
        def chat(**arguments):
            arguments["on_answer_delta"]("这是经过")
            arguments["on_answer_delta"]("证据校验的回答。")
            return payload

        runtime.return_value.chat.side_effect = chat
        response = client.post(
            reverse("copilot-chat-stream"),
            {"message": "分析项目"},
            format="json",
            HTTP_ACCEPT="text/event-stream",
        )
        content = b"".join(response.streaming_content).decode()

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    assert "event: status" in content
    assert "event: delta" in content
    assert "event: complete" in content
    assert "这是经过证据校验的回答" in content
    runtime.return_value.chat.assert_called_once_with(
        message="分析项目",
        provider_stream=True,
        on_answer_delta=runtime.return_value.chat.call_args.kwargs["on_answer_delta"],
    )


@pytest.mark.django_db
def test_copilot_history_is_private_readable_and_deletable():
    owner = get_user_model().objects.create_user(username="history-owner", password="password")
    stranger = get_user_model().objects.create_user(
        username="history-stranger", password="password"
    )
    conversation = CopilotConversation.objects.create(
        owner=owner,
        session_id="history-session-abcdefghijklmnop",
        title="分析项目",
    )
    CopilotMessage.objects.create(
        conversation=conversation,
        role=CopilotMessage.Role.USER,
        content="分析项目",
    )
    CopilotMessage.objects.create(
        conversation=conversation,
        role=CopilotMessage.Role.ASSISTANT,
        content="有证据的回答",
        response={"answer": "有证据的回答", "evidence": []},
    )
    client = APIClient()
    client.force_authenticate(stranger)
    assert client.get(reverse("copilot-history")).data["count"] == 0
    assert client.get(reverse("copilot-history-detail", args=[conversation.id])).status_code == 404
    delete_other = client.delete(reverse("copilot-history-detail", args=[conversation.id]))
    assert delete_other.status_code == 404

    client.force_authenticate(owner)
    history = client.get(reverse("copilot-history"))
    assert history.status_code == 200
    assert history.data["results"][0]["message_count"] == 2
    detail = client.get(reverse("copilot-history-detail", args=[conversation.id]))
    assert [item["role"] for item in detail.data["messages"]] == ["USER", "ASSISTANT"]
    with patch("apps.agent.api_views.RedisSessionStore.delete") as redis_delete:
        deleted = client.delete(reverse("copilot-history-detail", args=[conversation.id]))
    assert deleted.status_code == 204
    assert not CopilotConversation.objects.filter(id=conversation.id).exists()
    redis_delete.assert_called_once_with(conversation.session_id, owner.id)
