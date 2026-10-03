from apps.snapshots.locks import RedisRepositoryLock

from .fakes import FakeRedis


def test_redis_lock_uses_expected_key_ttl_and_excludes_second_worker() -> None:
    redis = FakeRedis()
    first = RedisRepositoryLock(42, client=redis)
    second = RedisRepositoryLock(42, client=redis)

    with first:
        assert first.acquired is True
        assert first.key == "agentGitHub:github:repo:42"
        with second:
            assert second.acquired is False

    assert first.key not in redis.values


def test_redis_lock_does_not_release_another_workers_token() -> None:
    redis = FakeRedis()
    lock = RedisRepositoryLock(7, client=redis)

    with lock:
        redis.values[lock.key] = "another-worker-token"

    assert redis.values[lock.key] == "another-worker-token"
