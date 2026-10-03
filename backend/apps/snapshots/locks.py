from types import TracebackType
from typing import Protocol, Self
from uuid import uuid4

from django.conf import settings
from redis import Redis


class RepositoryLockProtocol(Protocol):
    acquired: bool

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class RedisRepositoryLock:
    RELEASE_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """

    def __init__(self, repository_id: int, *, client: Redis | None = None) -> None:
        self.client = client or Redis.from_url(settings.CELERY_BROKER_URL)
        self.key = f"agentGitHub:github:repo:{repository_id}"
        self.token = uuid4().hex
        self.ttl = settings.REPOSITORY_SYNC_LOCK_TTL_SECONDS
        self.acquired = False

    def __enter__(self) -> Self:
        self.acquired = bool(self.client.set(self.key, self.token, nx=True, ex=self.ttl))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.acquired:
            self.client.eval(self.RELEASE_SCRIPT, 1, self.key, self.token)
            self.acquired = False
