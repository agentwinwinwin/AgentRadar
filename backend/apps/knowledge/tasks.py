import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone

from apps.github.client import GitHubClientError, RealGitHubClient
from apps.repositories.models import Repository
from apps.snapshots.locks import RedisRepositoryLock

from .models import KnowledgeSyncState
from .services import KnowledgeIngestionService

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="knowledge.sync_repository_knowledge", max_retries=3)
def sync_repository_knowledge(self, repository_id: int):
    try:
        repository = Repository.objects.get(pk=repository_id)
        with RedisRepositoryLock(repository_id) as lock:
            if not lock.acquired:
                raise GitHubClientError("repository sync lock unavailable")
            stats = KnowledgeIngestionService(RealGitHubClient()).sync_repository(repository)
        now = timezone.now()
        interval = settings.KNOWLEDGE_TIER_INTERVAL_HOURS[repository.monitoring_tier]
        KnowledgeSyncState.objects.update_or_create(
            repository=repository,
            defaults={
                "last_synced_at": now,
                "next_sync_at": now + timedelta(hours=interval),
                "last_status": "COMPLETED",
                "last_stats": stats,
            },
        )
        from apps.enterprise.tasks import calculate_repository_enterprise
        from apps.learning.tasks import calculate_repository_learning

        calculate_repository_learning.delay(repository_id)
        calculate_repository_enterprise.delay(repository_id)
        return stats
    except Repository.DoesNotExist:
        return {"status": "SKIPPED_NOT_FOUND"}
    except (GitHubClientError, DatabaseError) as exc:
        logger.warning("knowledge sync retry", extra={"repository_id": repository_id})
        raise self.retry(exc=exc, countdown=settings.REPOSITORY_SYNC_LOCK_RETRY_SECONDS) from exc


@shared_task(name="knowledge.embed_document")
def embed_document(document_id: int):
    return {"document_id": document_id, "status": "EMBEDDED_DURING_ATOMIC_INGESTION"}


@shared_task(name="knowledge.cleanup_stale_chunks")
def cleanup_stale_chunks():
    return {"deleted": 0, "policy": "cascade_on_document_change"}


@shared_task(name="knowledge.dispatch_knowledge_sync")
def dispatch_knowledge_sync():
    now = timezone.now()
    ids = list(
        Repository.objects.filter(
            dataset_pool_memberships__pool__pool_type="TRACKED",
            dataset_pool_memberships__pool__status="CONFIRMED",
            knowledge_sync_state__isnull=False,
            is_disabled=False,
            is_archived=False,
        )
        .filter(
            Q(knowledge_sync_state__next_sync_at__isnull=True)
            | Q(knowledge_sync_state__next_sync_at__lte=now)
        )
        .order_by("knowledge_sync_state__next_sync_at", "id")
        .values_list("id", flat=True)
        .distinct()[: settings.KNOWLEDGE_SYNC_BATCH_SIZE]
    )
    for repository_id in ids:
        sync_repository_knowledge.delay(repository_id)
    return {"dispatched": len(ids)}
