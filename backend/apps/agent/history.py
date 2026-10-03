from __future__ import annotations

import re
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.repositories.models import Repository

from .models import CopilotConversation, CopilotMessage


class CopilotHistoryService:
    REPOSITORY_NAME = re.compile(r"(?<![\w.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?![\w.-])")
    @staticmethod
    @transaction.atomic
    def persist_turn(
        *,
        owner_id: int,
        session_id: str,
        question: str,
        result: dict[str, Any],
    ) -> CopilotConversation:
        conversation, _ = CopilotConversation.objects.get_or_create(
            owner_id=owner_id,
            session_id=session_id,
            defaults={"title": question.strip()[:120]},
        )
        persisted_result = {
            key: result[key]
            for key in (
                "answer",
                "intent",
                "intent_confidence",
                "skill",
                "skill_version",
                "status",
                "recommendations",
                "warnings",
                "evidence",
                "repository_links",
                "trace_id",
                "session_id",
            )
            if key in result
        }
        CopilotMessage.objects.bulk_create(
            [
                CopilotMessage(
                    conversation=conversation,
                    role=CopilotMessage.Role.USER,
                    content=question,
                ),
                CopilotMessage(
                    conversation=conversation,
                    role=CopilotMessage.Role.ASSISTANT,
                    content=result["answer"],
                    response=persisted_result,
                ),
            ]
        )
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=("updated_at",))
        return conversation

    @staticmethod
    def list_for_owner(owner_id: int):
        return CopilotConversation.objects.filter(owner_id=owner_id).prefetch_related("messages")

    @staticmethod
    def get_for_owner(owner_id: int, conversation_id: int) -> CopilotConversation:
        return CopilotConversation.objects.prefetch_related("messages").get(
            owner_id=owner_id,
            id=conversation_id,
        )

    @staticmethod
    def delete_for_owner(owner_id: int, conversation_id: int) -> str:
        conversation = CopilotConversation.objects.get(owner_id=owner_id, id=conversation_id)
        session_id = conversation.session_id
        conversation.delete()
        return session_id

    @classmethod
    def repository_links_for_messages(cls, messages) -> list[dict[str, Any]]:
        candidates: set[str] = set()
        for message in messages:
            if message.role == CopilotMessage.Role.ASSISTANT:
                candidates.update(cls.REPOSITORY_NAME.findall(message.content))
            if len(candidates) >= 20:
                break
        repositories = Repository.objects.filter(
            full_name__in=list(candidates)[:20],
            is_disabled=False,
        ).values("id", "full_name")
        return [
            {"repository_id": item["id"], "full_name": item["full_name"]}
            for item in repositories
        ]
