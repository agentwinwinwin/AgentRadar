from unittest.mock import Mock, patch

import pytest

from apps.common.task_dispatch import dispatch_unique_repository_task


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.deleted: list[str] = []

    def set(self, key, value, *, nx, ex):
        assert nx is True
        assert ex > 0
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script, key_count, key, token):
        assert key_count == 1
        if self.values.get(key) == token:
            self.values.pop(key)
            self.deleted.append(key)
            return 1
        return 0


def test_repository_task_dispatch_is_coalesced(settings):
    settings.REPOSITORY_TASK_COALESCE_TTL_SECONDS = 900
    redis = FakeRedis()
    task = Mock()
    with patch("apps.common.task_dispatch.Redis.from_url", return_value=redis):
        assert dispatch_unique_repository_task(task, 42, purpose="trend-score") is True
        assert dispatch_unique_repository_task(task, 42, purpose="trend-score") is False

    task.delay.assert_called_once_with(42)


def test_repository_task_dispatch_releases_key_when_enqueue_fails(settings):
    settings.REPOSITORY_TASK_COALESCE_TTL_SECONDS = 900
    redis = FakeRedis()
    task = Mock()
    task.delay.side_effect = RuntimeError("broker unavailable")
    with (
        patch("apps.common.task_dispatch.Redis.from_url", return_value=redis),
        pytest.raises(RuntimeError, match="broker unavailable"),
    ):
        dispatch_unique_repository_task(task, 7, purpose="alert-evaluation")

    assert not redis.values
    assert redis.deleted == ["agentradar:celery:pending:alert-evaluation:7"]
