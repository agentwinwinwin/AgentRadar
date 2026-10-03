import pytest
from django.contrib.auth import get_user_model

from apps.agent.history import CopilotHistoryService
from apps.agent.models import CopilotConversation, CopilotMessage


@pytest.mark.django_db
def test_persist_turn_appends_messages_and_keeps_first_question_as_title():
    user = get_user_model().objects.create_user(username="history-service", password="password")
    result = {
        "answer": "第一个回答",
        "intent": "PROJECT_ANALYSIS",
        "intent_confidence": 0.9,
        "skill": "project-analysis",
        "skill_version": "project-analysis-v1.1.0",
        "status": "COMPLETED",
        "recommendations": [],
        "warnings": [],
        "evidence": [],
        "trace_id": "trace-1",
        "session_id": "persist-session-abcdefghijklmnop",
        "trace": {"must_not": "be persisted"},
    }

    CopilotHistoryService.persist_turn(
        owner_id=user.id,
        session_id=result["session_id"],
        question="第一个问题",
        result=result,
    )
    result["answer"] = "第二个回答"
    CopilotHistoryService.persist_turn(
        owner_id=user.id,
        session_id=result["session_id"],
        question="第二个问题",
        result=result,
    )

    conversation = CopilotConversation.objects.get(owner=user)
    assert conversation.title == "第一个问题"
    assert conversation.messages.count() == 4
    assistant = conversation.messages.filter(role=CopilotMessage.Role.ASSISTANT).first()
    assert "trace" not in assistant.response
