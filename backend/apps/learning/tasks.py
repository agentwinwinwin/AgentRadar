import logging

from celery import shared_task
from django.conf import settings
from django.db import DatabaseError

from apps.github.client import (
    GitHubClientError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    RealGitHubClient,
)
from apps.repositories.models import Repository
from apps.snapshots.locks import RedisRepositoryLock

from .enrichment import AssessmentEnrichmentService
from .services import LearningService

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="learning.calculate_repository_learning", max_retries=3)
def calculate_repository_learning(self, repository_id: int):
    try:
        with RedisRepositoryLock(repository_id) as lock:
            if not lock.acquired:
                raise DatabaseError("repository score lock unavailable")
            score = LearningService().calculate_repository(repository_id)
        return {
            "id": score.id,
            "repository_id": repository_id,
            "score": str(score.score) if score.score is not None else None,
        }
    except Repository.DoesNotExist:
        return {"repository_id": repository_id, "status": "SKIPPED_NOT_FOUND"}
    except DatabaseError as exc:
        raise self.retry(exc=exc, countdown=10) from exc


@shared_task(name="learning.calculate_learning_score")
def calculate_learning_score(repository_id: int):
    return calculate_repository_learning.run(repository_id)


@shared_task(name="learning.dispatch_learning_scoring")
def dispatch_learning_scoring(after_id: int = 0):
    ids = list(
        Repository.objects.filter(is_disabled=False, is_fork=False, id__gt=after_id)
        .order_by("id")
        .values_list("id", flat=True)[: settings.ASSESSMENT_SCORING_BATCH_SIZE]
    )
    for repository_id in ids:
        calculate_repository_learning.delay(repository_id)
    if len(ids) == settings.ASSESSMENT_SCORING_BATCH_SIZE:
        dispatch_learning_scoring.apply_async(args=[ids[-1]], countdown=5)
    return {"dispatched": len(ids), "next_after_id": ids[-1] if ids else None}


@shared_task(name="learning.calculate_all_learning_scores")
def calculate_all_learning_scores():
    dispatch_learning_scoring.delay()
    return {"status": "BATCH_DISPATCHED"}


@shared_task(bind=True, name="learning.enrich_repository_score_evidence", max_retries=3)
def enrich_repository_score_evidence(self, repository_id: int):
    try:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        with RedisRepositoryLock(repository_id) as lock:
            if not lock.acquired:
                raise DatabaseError("repository enrichment lock unavailable")
            result = AssessmentEnrichmentService(RealGitHubClient()).enrich(repository)
        calculate_repository_learning.delay(repository_id)
        from apps.enterprise.tasks import calculate_repository_enterprise

        calculate_repository_enterprise.delay(repository_id)
        return {
            "repository_id": repository_id,
            "requests": result.requests,
            "status": result.evidence.status,
        }
    except Repository.DoesNotExist:
        return {"repository_id": repository_id, "status": "SKIPPED_NOT_FOUND"}
    except GitHubNotFoundError:
        repository = Repository.objects.filter(pk=repository_id).first()
        if repository:
            AssessmentEnrichmentService(RealGitHubClient()).mark_not_found(repository)
        return {"repository_id": repository_id, "status": "NOT_FOUND"}
    except GitHubRateLimitError as exc:
        logger.warning(
            "assessment enrichment paused for rate limit", extra={"repository_id": repository_id}
        )
        raise self.retry(exc=exc, countdown=300) from exc
    except (GitHubClientError, DatabaseError) as exc:
        raise self.retry(exc=exc, countdown=30) from exc


@shared_task(name="learning.dispatch_assessment_enrichment")
def dispatch_assessment_enrichment():
    client = RealGitHubClient()
    resources = client.get_rate_limit()["resources"]
    remaining = int(resources.get("core", {}).get("remaining", 0))
    budget = max(0, remaining - settings.GITHUB_CORE_MIN_REMAINING)
    limit = min(settings.ASSESSMENT_ENRICHMENT_BATCH_SIZE, budget // 3)
    ids = list(
        Repository.objects.filter(
            is_disabled=False,
            is_fork=False,
            assessment_evidence__isnull=True,
        )
        .order_by("id")
        .values_list("id", flat=True)[:limit]
    )
    for repository_id in ids:
        enrich_repository_score_evidence.delay(repository_id)
    return {
        "dispatched": len(ids),
        "core_remaining": remaining,
        "budget_reserved": settings.GITHUB_CORE_MIN_REMAINING,
    }
