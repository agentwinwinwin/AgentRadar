from types import TracebackType
from typing import Self


class FakeRepositoryLock:
    def __init__(self, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.exited = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exited = True


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        assert nx is True
        assert ex > 0
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script: str, key_count: int, key: str, token: str) -> int:
        assert script
        assert key_count == 1
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0
