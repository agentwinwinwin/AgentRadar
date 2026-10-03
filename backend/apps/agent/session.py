from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any, Protocol

from django.conf import settings
from redis import Redis


class SessionStore(Protocol):
    def get(self, session_id: str, owner_id: int | None = None) -> dict[str, Any]: ...
    def save(self, session_id: str, data: dict[str, Any], owner_id: int | None = None) -> None: ...
    def delete(self, session_id: str, owner_id: int | None = None) -> None: ...


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


class RedisSessionStore:
    PREFIX = "agentradar:copilot:session:"

    def __init__(self, client: Redis | None = None) -> None:
        self.client = client or Redis.from_url(settings.REDIS_URL, decode_responses=True)

    @staticmethod
    def _key(session_id: str, owner_id: int | None) -> str:
        if owner_id is None:
            raise ValueError("Authenticated session owner is required")
        return f"{RedisSessionStore.PREFIX}{owner_id}:{session_id}"

    def get(self, session_id: str, owner_id: int | None = None) -> dict[str, Any]:
        raw = self.client.get(self._key(session_id, owner_id))
        return json.loads(raw) if raw else {}

    def save(self, session_id: str, data: dict[str, Any], owner_id: int | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        payload = {
            "session_id": session_id,
            "recent_turns": data.get("recent_turns", [])[-settings.AGENT_SESSION_MAX_TURNS :],
            "resolved_entities": data.get("resolved_entities", {}),
            "user_constraints": data.get("user_constraints", {}),
            "last_intent": data.get("last_intent"),
            "created_at": data.get("created_at", now),
            "updated_at": now,
        }
        self.client.setex(
            self._key(session_id, owner_id),
            settings.AGENT_SESSION_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )

    def delete(self, session_id: str, owner_id: int | None = None) -> None:
        self.client.delete(self._key(session_id, owner_id))
