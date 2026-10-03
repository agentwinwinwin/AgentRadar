import logging

from celery import shared_task
from django.conf import settings
from django.db import DatabaseError, models
from django.utils import timezone

from apps.github.client import GitHubClientError, RealGitHubClient
from apps.repositories.models import Repository

from .locks import RedisRepositoryLock
from .monitoring import record_snapshot_schedule, refresh_repository_monitoring
from .services import SnapshotService

logger = logging.getLogger(__name__)


class RepositoryLockUnavailable(RuntimeError):
    pass


@shared_task(name="snapshots.snapshot_persisted")
def snapshot_persisted(snapshot_id: int) -> None:
    logger.info("repository snapshot committed", extra={"snapshot_id": snapshot_id})
    from .models import RepositorySnapshot

    repository_id = (
        RepositorySnapshot.objects.filter(pk=snapshot_id)
        .values_list("repository_id", flat=True)
        .first()
    )
    if repository_id is not None:
        from apps.trends.tasks import dispatch_trend_score

        dispatch_trend_score(repository_id)


@shared_task(
    bind=True,
    name="snapshots.create_repository_snapshot",
    max_retries=3,
    soft_time_limit=270,
    time_limit=300,
)
def create_repository_snapshot(self, repository_id: int) -> dict[str, int | bool]:
    try:
        repository = Repository.objects.get(pk=repository_id)
        with RedisRepositoryLock(repository_id) as lock:
            if not lock.acquired:
                raise RepositoryLockUnavailable(f"repository {repository_id} is already syncing")
            result = SnapshotService(RealGitHubClient()).sync_and_snapshot(
                repository,
                on_committed=snapshot_persisted.delay,
            )
            record_snapshot_schedule(repository_id, result.snapshot)
        return {"snapshot_id": result.snapshot.id, "created": result.created}
    except Repository.DoesNotExist:
        logger.warning("repository not found", extra={"repository_id": repository_id})
        return {"repository_id": repository_id, "created": False}
    except (RepositoryLockUnavailable, GitHubClientError, DatabaseError) as exc:
        logger.warning(
            "repository snapshot retry",
            extra={"repository_id": repository_id, "error": str(exc)},
        )
        raise self.retry(
            exc=exc,
            countdown=settings.REPOSITORY_SYNC_LOCK_RETRY_SECONDS,
        ) from exc


@shared_task(name="snapshots.dispatch_due_snapshots")
def dispatch_due_snapshots() -> dict[str, int | bool]:
    now = timezone.now()
    repository_ids = list(
        Repository.objects.filter(
            monitoring_enabled=True,
            is_archived=False,
            is_disabled=False,
        )
        .filter(models.Q(next_snapshot_at__isnull=True) | models.Q(next_snapshot_at__lte=now))
        .order_by("next_snapshot_at", "id")
        .values_list("id", flat=True)[: settings.SNAPSHOT_DISPATCH_BATCH_SIZE]
    )
    if not repository_ids:
        return {"dispatched": 0, "budget_ok": True}
    try:
        resources = RealGitHubClient().get_rate_limit()["resources"]
    except GitHubClientError:
        logger.warning("snapshot dispatcher paused because GitHub budget could not be read")
        return {"dispatched": 0, "budget_ok": False}
    core = resources.get("core", {})
    if int(core.get("remaining", 0)) <= settings.GITHUB_CORE_MIN_REMAINING:
        logger.warning("snapshot dispatcher paused for GitHub core budget")
        return {"dispatched": 0, "budget_ok": False}
    available = max(
        0,
        int(core.get("remaining", 0)) - settings.GITHUB_CORE_MIN_REMAINING,
    )
    repository_ids = repository_ids[:available]
    for repository_id in repository_ids:
        create_repository_snapshot.delay(repository_id)
    return {"dispatched": len(repository_ids), "budget_ok": True}


# Backwards-compatible callable for operators; no longer registered in Beat.
capture_due_repository_snapshots = dispatch_due_snapshots


@shared_task(name="snapshots.reassess_monitoring_tiers")
def reassess_monitoring_tiers() -> dict[str, object]:
    from apps.capabilities.locks import RedisCapabilityLock

    with RedisCapabilityLock("monitoring-tier-reassessment", ttl=3600) as lock:
        if not lock.acquired:
            return {"status": "SKIPPED", "reason": "reassessment_lock_busy"}
        changed = 0
        tiers: dict[str, int] = {}
        repositories = Repository.objects.filter(is_fork=False).order_by("id")
        for repository in repositories.iterator(chunk_size=200):
            previous = repository.monitoring_tier
            assessment = refresh_repository_monitoring(repository.id)
            changed += int(previous != assessment.tier)
            tiers[str(assessment.tier)] = tiers.get(str(assessment.tier), 0) + 1
    return {
        "status": "COMPLETED",
        "evaluated": sum(tiers.values()),
        "changed": changed,
        "tiers": tiers,
    }
