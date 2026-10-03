import json
import queue
import threading

from django.db import close_old_connections
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .api_serializers import CopilotChatSerializer
from .history import CopilotHistoryService
from .models import CopilotConversation
from .runtime import AgentError, PMCopilotRuntime
from .session import RedisSessionStore


class CopilotChatView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = CopilotChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = PMCopilotRuntime(actor_user_id=request.user.id).chat(
                **serializer.validated_data
            )
        except AgentError as exc:
            return Response(
                {"error_code": exc.code, "message": exc.message},
                status=exc.status_code,
            )
        return Response(result, status=status.HTTP_200_OK)


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class EventStreamRenderer(BaseRenderer):
    """Allow DRF content negotiation for browser SSE requests."""

    media_type = "text/event-stream"
    format = "event-stream"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""
        message = data.get("message") or data.get("detail") or "流式请求失败"
        return _sse("error", {"message": message}).encode(self.charset)


class CopilotChatStreamView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"
    renderer_classes = [EventStreamRenderer]

    def post(self, request):
        serializer = CopilotChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        arguments = dict(serializer.validated_data)
        owner_id = request.user.id

        def events():
            yield _sse("status", {"message": "正在识别意图并调用只读工具…"})
            stream_queue: queue.Queue[tuple[str, object]] = queue.Queue()

            def run() -> None:
                close_old_connections()
                try:
                    result = PMCopilotRuntime(actor_user_id=owner_id).chat(
                        **arguments,
                        provider_stream=True,
                        on_answer_delta=lambda text: stream_queue.put(("delta", text)),
                    )
                    stream_queue.put(("complete", result))
                except AgentError as exc:
                    stream_queue.put(
                        ("error", {"error_code": exc.code, "message": exc.message})
                    )
                except Exception:
                    stream_queue.put(
                        (
                            "error",
                            {
                                "error_code": "INTERNAL_ERROR",
                                "message": "智能分析暂时无法完成。",
                            },
                        )
                    )
                finally:
                    close_old_connections()

            threading.Thread(target=run, daemon=True, name="copilot-sse").start()
            generation_started = False
            while True:
                try:
                    event, data = stream_queue.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                if event == "delta" and not generation_started:
                    generation_started = True
                    yield _sse(
                        "status",
                        {"message": "证据校验完成，DeepSeek 正在实时生成回答…"},
                    )
                yield _sse(event, {"text": data} if event == "delta" else data)
                if event in {"complete", "error"}:
                    return

        response = StreamingHttpResponse(events(), content_type="text/event-stream; charset=utf-8")
        response["Cache-Control"] = "no-cache, no-transform"
        response["X-Accel-Buffering"] = "no"
        return response


def _conversation_data(conversation: CopilotConversation, *, include_messages: bool) -> dict:
    data = {
        "id": conversation.id,
        "session_id": conversation.session_id,
        "title": conversation.title,
        "message_count": conversation.messages.count(),
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }
    if include_messages:
        messages = list(conversation.messages.all())
        fallback_links = CopilotHistoryService.repository_links_for_messages(messages)
        data["messages"] = [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "response": (
                    {
                        **message.response,
                        "repository_links": message.response.get("repository_links")
                        or fallback_links,
                    }
                    if message.response
                    else None
                ),
                "created_at": message.created_at,
            }
            for message in messages
        ]
    return data


class CopilotConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = CopilotHistoryService.list_for_owner(request.user.id)
        paginator = PageNumberPagination()
        paginator.page_size = 30
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [_conversation_data(item, include_messages=False) for item in page]
        )


class CopilotConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _get(owner_id: int, conversation_id: int) -> CopilotConversation:
        try:
            return CopilotHistoryService.get_for_owner(owner_id, conversation_id)
        except CopilotConversation.DoesNotExist as exc:
            raise NotFound("历史会话不存在") from exc

    def get(self, request, conversation_id: int):
        return Response(
            _conversation_data(self._get(request.user.id, conversation_id), include_messages=True)
        )

    def delete(self, request, conversation_id: int):
        self._get(request.user.id, conversation_id)
        session_id = CopilotHistoryService.delete_for_owner(request.user.id, conversation_id)
        RedisSessionStore().delete(session_id, request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
