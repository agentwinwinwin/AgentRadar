import logging

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from apps.agent.llm import LLMError
from apps.github.client import GitHubClientError, RealGitHubClient
from apps.snapshots.locks import RedisRepositoryLock

from .continuous import ContinuousDiscoveryService, GitHubBudgetUnavailable
from .localization import RepositoryLocalizationService
from .models import Repository

logger = logging.getLogger(__name__)


def _run(task, mode: str) -> dict[str, int | str]:
    try:
        result = ContinuousDiscoveryService(RealGitHubClient()).discover(mode=mode)
        return result.__dict__
    except GitHubBudgetUnavailable:
        logger.warning("continuous discovery paused for GitHub budget", extra={"mode": mode})
        return {"status": "PAUSED_RATE_LIMIT", "created": 0}
    except GitHubClientError as exc:
        logger.warning("continuous discovery retry", extra={"mode": mode})
        raise task.retry(
            exc=exc,
            countdown=settings.REPOSITORY_SYNC_LOCK_RETRY_SECONDS,
        ) from exc


@shared_task(bind=True, name="repositories.discover_new_repositories", max_retries=3)
def discover_new_repositories(self) -> dict[str, int | str]:
    return _run(self, "new")


@shared_task(bind=True, name="repositories.refresh_recent_repositories", max_retries=3)
def refresh_recent_repositories(self) -> dict[str, int | str]:
    return _run(self, "recent")


@shared_task(bind=True, name="repositories.localize_repository", max_retries=3)
def localize_repository(self, repository_id: int, expected_source_hash: str) -> dict[str, str]:
    queue_key = f"agentradar:localization:queued:{repository_id}:{expected_source_hash}"
    try:
        repository = Repository.objects.prefetch_related("topics").get(
            pk=repository_id, is_disabled=False
        )
        service = RepositoryLocalizationService()
        _, current_source_hash = service.source(repository)
        if current_source_hash != expected_source_hash:
            cache.delete(queue_key)
            return {"status": "SKIPPED_STALE_SOURCE"}
        with RedisRepositoryLock(repository_id) as lock:
            if not lock.acquired:
                raise LLMError("LOCALIZATION_LOCKED", "repository lock unavailable")
            result = service.localize(repository)
        cache.delete(queue_key)
        return {"status": result["localization_status"]}
    except Repository.DoesNotExist:
        cache.delete(queue_key)
        return {"status": "SKIPPED_NOT_FOUND"}
    except LLMError as exc:
        logger.warning(
            "repository localization retry",
            extra={"repository_id": repository_id, "code": exc.code},
        )
        raise self.retry(
            exc=exc,
            countdown=settings.REPOSITORY_SYNC_LOCK_RETRY_SECONDS,
        ) from exc
