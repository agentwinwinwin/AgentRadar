from contextvars import ContextVar

actor_user_id: ContextVar[int | None] = ContextVar("actor_user_id", default=None)


class ActorRequired(RuntimeError):
    pass
