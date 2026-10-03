from types import TracebackType
from typing import Self
from uuid import uuid4

from django.conf import settings
from redis import Redis


class RedisTrainingLock:
    RELEASE_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """

    def __init__(self, *, client: Redis | None = None, ttl: int = 7200) -> None:
        self.client = client or Redis.from_url(settings.CELERY_BROKER_URL)
        self.key = "agentGitHub:forecast:training"
        self.token = uuid4().hex
        self.ttl = ttl
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


class RedisPredictionRolloutLock(RedisTrainingLock):
    def __init__(self, model_version: str, *, client: Redis | None = None, ttl: int = 7200) -> None:
        super().__init__(client=client, ttl=ttl)
        self.key = f"agentGitHub:forecast:star-rollout:{model_version}"
