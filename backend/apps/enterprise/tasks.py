from celery import shared_task
from django.conf import settings
from django.db import DatabaseError

from apps.repositories.models import Repository
from apps.snapshots.locks import RedisRepositoryLock

from .services import EnterpriseService


@shared_task(bind=True, name="enterprise.calculate_repository_enterprise", max_retries=3)
def calculate_repository_enterprise(self, repository_id: int):
    try:
        with RedisRepositoryLock(repository_id) as lock:
            if not lock.acquired:
                raise DatabaseError("repository score lock unavailable")
            score = EnterpriseService().calculate_repository(repository_id)
        return {
            "id": score.id,
            "repository_id": repository_id,
            "score": str(score.score) if score.score is not None else None,
        }
    except Repository.DoesNotExist:
        return {"repository_id": repository_id, "status": "SKIPPED_NOT_FOUND"}
    except DatabaseError as exc:
        raise self.retry(exc=exc, countdown=10) from exc


@shared_task(name="enterprise.calculate_enterprise_score")
def calculate_enterprise_score(repository_id: int):
    return calculate_repository_enterprise.run(repository_id)


@shared_task(name="enterprise.dispatch_enterprise_scoring")
def dispatch_enterprise_scoring(after_id: int = 0):
    ids = list(
        Repository.objects.filter(is_disabled=False, is_fork=False, id__gt=after_id)
        .order_by("id")
        .values_list("id", flat=True)[: settings.ASSESSMENT_SCORING_BATCH_SIZE]
    )
    for repository_id in ids:
        calculate_repository_enterprise.delay(repository_id)
    if len(ids) == settings.ASSESSMENT_SCORING_BATCH_SIZE:
        dispatch_enterprise_scoring.apply_async(args=[ids[-1]], countdown=5)
    return {"dispatched": len(ids), "next_after_id": ids[-1] if ids else None}


@shared_task(name="enterprise.calculate_all_enterprise_scores")
def calculate_all_enterprise_scores():
    dispatch_enterprise_scoring.delay()
    return {"status": "BATCH_DISPATCHED"}
